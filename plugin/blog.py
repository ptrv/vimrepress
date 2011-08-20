# -*- coding: utf-8 -*-
import urllib, urllib2, vim, xml.dom.minidom, xmlrpclib, sys, string, re, os, mimetypes, webbrowser, tempfile, time
try:
    import markdown
except ImportError:
    try:
        import markdown2 as markdown
    except ImportError:
        class markdown_stub(object):
            def markdown(self, n):
                raise VimPressException("The package python-markdown is required and is either not present or not properly installed.")
        markdown = markdown_stub()


def exception_check(func):
    def __check(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except VimPressException, e:
            sys.stderr.write(str(e))
        except xmlrpclib.Fault, e:
            sys.stderr.write("xmlrpc error: %s" % e.faultString.encode("utf-8"))
        except xmlrpclib.ProtocolError, e:
            sys.stderr.write("xmlrpc error: %s %s" % (e.url, e.errmsg))
        except IOError, e:
            sys.stderr.write("network error: %s" % e)

    return __check

#################################################
# Helper Classes
#################################################

class VimPressException(Exception):
    pass

class VimPressFailedGetMkd(VimPressException):
    pass
class DataObject(object):

    #CONST
    DEFAULT_LIST_COUNT = "15"
    IMAGE_TEMPLATE = '<a href="%(url)s"><img title="%(file)s" alt="%(file)s" src="%(url)s" class="aligncenter" /></a>'
    MARKER = dict(bg = "=========== Meta ============", 
                  mid = "=============================", 
                  ed = "========== Content ==========",
                  more = '"====== Press Here for More ======',
                  list_title = '"====== List of %(edit_type)s(s) in %(blog_url)s =========')
    LIST_VIEW_KEY_MAP = dict(enter = "<enter>", delete = "<delete>")
    DEFAULT_META = dict(strid = "", title = "", slug = "", 
                        cats = "", tags = "", editformat = "Markdown", 
                        edittype = "post", textattach = '')
    TAG_STRING = "<!-- #VIMPRESS_TAG# %(url)s %(file)s -->"
    TAG_RE = re.compile(TAG_STRING % dict(url = '(?P<mkd_url>\S+)', file = '(?P<mkd_name>\S+)'))

    #Temp variables.
    blog_username = None
    blog_password = None
    blog_url = None
    conf_index = 0
    view = 'edit'
    vimpress_temp_dir = ''
    mw_api = None
    wp_api = None
    posts_max = -1
    posts_titles = []

    def is_api_ready(self):
        return not (self.wp_api is None or self.mw_api is None)

    @exception_check
    def blog_update_config(self):
        """
        Updates the script's configuration variables.
        """
        try:
            config = vim.eval("VIMPRESS")[self.conf_index]

            self.blog_username = config['username']
            self.blog_password = config.get('password', '')
            self.blog_url = config['blog_url']

            sys.stdout.write("Connecting to %s \n" % self.blog_url)

            if self.blog_password == '':
               self.blog_password = vim_input("Enter password for %s" % self.blog_url, True)
            self.mw_api = xmlrpclib.ServerProxy("%s/xmlrpc.php" % self.blog_url).metaWeblog
            self.wp_api = xmlrpclib.ServerProxy("%s/xmlrpc.php" % self.blog_url).wp

            # Setting tags and categories for completefunc
            terms = []
            terms.extend([i["description"].encode("utf-8") 
                for i in self.mw_api.getCategories('', self.blog_username, self.blog_password)])

            # adding tags may make the menu too much items to choose.
            #terms.extend([i["name"].encode("utf-8") for i in self.wp_api.getTags('', self.blog_username, self.blog_password)])
            vim.command('let s:completable = "%s"' % '|'.join(terms))

        except vim.error:
            raise VimPressException("Could not find vimpress configuration. Please read ':help vimpress' for more information.")
        except KeyError, e:
            raise VimPressException("Configuration error: %s" % e)

    @exception_check
    def config_switch(self, index = -1):
        try:
            index = int(index)
        except ValueError:
            raise VimPressException("Invalid Index: %s" % index)

        conf = vim.eval("VIMPRESS")
         # Next conf
        if index < 0:
            self.conf_index += 1
            if self.conf_index >= len(conf):
                self.conf_index = 0

         # User enter index
        else:
            if index >= len(conf):
                raise VimPressException("Invalid Index: %d" % index)
            self.conf_index = index

        self.blog_update_config()
        sys.stdout.write("Vimpress switched to '%s'@'%s'\n" % (self.blog_username, self.blog_url))


#################################################
# Golbal Variables
#################################################
g_data = DataObject()

#################################################
# Helper Functions
#################################################

def vim_encoding_check(func):
    def __check(*args, **kw):
        orig_enc = vim.eval("&encoding") 
        if orig_enc != "utf-8":
            modified = vim.eval("&modified")
            buf_list = '\n'.join(vim.current.buffer).decode(orig_enc).encode('utf-8').split('\n')
            del vim.current.buffer[:]
            vim.command("setl encoding=utf-8")
            vim.current.buffer[0] = buf_list[0]
            if len(buf_list) > 1:
                vim.current.buffer.append(buf_list[1:])
            if modified == '0':
                vim.command('setl nomodified')
        return func(*args, **kw)
    return __check

def view_switch(view = "", assert_view = "", reset = False):
    def switch(func):
        def __run(*args, **kw):
            if assert_view != '':
                if g_data.view != assert_view:
                    raise VimPressException("Command only available at '%s' view." % assert_view)

            if func.func_name == "blog_new":
                if g_data.view == "list":
                    kw["currentContent"] = ['']
                else:
                    kw["currentContent"] = vim.current.buffer[:]
            elif func.func_name == "blog_config_switch":
                if g_data.view == "list":
                    kw["refresh_list"] = True

            if reset:
                g_data.posts_max = -1
                g_data.posts_titles = None

            if view != '':
                #Switching view
                if g_data.view != view:

                    #from list view
                    if g_data.view == "list":
                        for v in g_data.LIST_VIEW_KEY_MAP.values():
                            if vim.eval("mapcheck('%s')" % v):
                                vim.command('unmap <buffer> %s' % v)

                    g_data.view = view

            return func(*args, **kw)
        return __run
    return switch


def blog_meta_parse():
    """
    Parses the meta data region of a blog editing buffer.
    @returns a dictionary of the meta data
    """
    meta = dict()
    start = 0
    while not vim.current.buffer[start][1:].startswith(g_data.MARKER['bg']):
        start +=1

    end = start + 1
    while not vim.current.buffer[end][1:].startswith(g_data.MARKER['ed']):
        if not vim.current.buffer[end].startswith('"===='):
            line = vim.current.buffer[end][1:].strip().split(":")
            k, v = line[0].strip().lower(), ':'.join(line[1:])
            meta[k.strip().lower()] = v.strip()
        end += 1

    meta["post_begin"] = end + 1
    return meta

def blog_meta_area_update(**kw):
    """
    Updates the meta data region of a blog editing buffer.
    @params **kwargs - keyworded arguments
    """
    start = 0
    while not vim.current.buffer[start][1:].startswith(g_data.MARKER['bg']):
        start +=1

    end = start + 1
    while not vim.current.buffer[end][1:].startswith(g_data.MARKER['ed']):
        if not vim.current.buffer[end].startswith('"===='):
            line = vim.current.buffer[end][1:].strip().split(":")
            k, v = line[0].strip().lower(), ':'.join(line[1:])
            if k in kw:
                new_line = "\"%s: %s" % (line[0], kw[k])
                vim.current.buffer[end] = new_line
        end += 1

def blog_fill_meta_area(meta):
    """
    Creates the meta data region for a blog editing buffer using a dictionary of meta data. Empty keywords
    are replaced by default values from the default_meta variable.
    @params meta - a dictionary of meta data
    """
    for k in g_data.DEFAULT_META.keys():
        if k not in meta:
            meta[k] = g_data.DEFAULT_META[k]

    meta.update(g_data.MARKER)
    template = dict( \
        post = \
""""%(bg)s
"StrID : %(strid)s
"Title : %(title)s
"Slug  : %(slug)s
"Cats  : %(cats)s
"Tags  : %(tags)s
"%(mid)s
"EditType   : %(edittype)s
"EditFormat : %(editformat)s
"TextAttach : %(textattach)s
"%(ed)s""", 
        page = \
""""%(bg)s
"StrID : %(strid)s
"Title : %(title)s
"Slug  : %(slug)s
"%(mid)s
"EditType   : %(edittype)s
"EditFormat : %(editformat)s
"TextAttach : %(textattach)s
"%(ed)s""") 

    if meta["edittype"] not in ("post", "page"):
        raise VimPressException("Invalid option: %(edittype)s " % meta)
    meta_text = template[meta["edittype"].lower()] % meta
    meta = meta_text.split('\n')
    vim.current.buffer[0] = meta[0]
    vim.current.buffer.append(meta[1:])

def blog_get_mkd_attachment(post):
    """
    Attempts to find a vimpress tag containing a URL for a markdown attachment and parses it.
    @params post - the content of a post
    @returns a dictionary with the attachment's content and URL
    """
    attach = dict()
    try:
        lead = post.rindex("<!-- ")
        data = re.search(g_data.TAG_RE, post[lead:])
        if data is None:
            raise ValueError()
        attach.update(data.groupdict())
        attach["mkd_rawtext"] = urllib2.urlopen(attach["mkd_url"]).read()
    except ValueError, e:
        return dict()
    except IOError:
        raise VimPressFailedGetMkd("The attachment URL was found but was unable to be read.")

    return attach


def blog_wise_open_view():
    """
    Wisely decides whether to wipe out the content of current buffer or open a new splited window.
    """
    if vim.current.buffer.name is None and \
            (vim.eval('&modified') == '0' or \
                len(vim.current.buffer) == 1):
        vim.command('setl modifiable')
        del vim.current.buffer[:]
        vim.command('setl nomodified')
    else:
        vim.command(":new")
    vim.command('setl syntax=blogsyntax')
    vim.command('setl completefunc=Completable')

def blog_upload_markdown_attachment(post_id, attach_name, mkd_rawtext):
    """
    Uploads the markdown attachment.
    @params post_id     - the id of the post or page
            attach_name - the name of the attachment
            mkd_rawtext - the Markdown content
    """
    bits = xmlrpclib.Binary(mkd_rawtext)

    # New Post, new file
    if post_id == '' or attach_name == '':
        attach_name = "vimpress_%s_mkd.txt" % hex(int(time.time()))[2:]
        overwrite = False
    else:
        overwrite = True

    sys.stdout.write("Markdown file uploading ... ")
    result = g_data.mw_api.newMediaObject(1, g_data.blog_username, g_data.blog_password, 
                dict(name = attach_name, 
                    type = "text/plain", bits = bits, 
                    overwrite = overwrite))
    sys.stdout.write("%s\n" % result["file"])
    return result

@vim_encoding_check
def vim_input(message = 'input', secret = False):
    vim.command('call inputsave()')
    vim.command("let user_input = %s('%s :')" % (("inputsecret" if secret else "input"), message))
    vim.command('call inputrestore()')
    return vim.eval('user_input')

def html_preview(text_html, meta):
    """
    Opens a browser with a local preview of the content.
    @params text_html - the html content
            meta      - a dictionary of the meta data
    """
    if g_data.vimpress_temp_dir == '':
        g_data.vimpress_temp_dir = tempfile.mkdtemp(suffix="vimpress")
    
    html = \
"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html><head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
<title>Vimpress Local Preview: %(title)s</title>
<style type="text/css"> ul, li { margin: 1em; } :link,:visited { text-decoration:none } h1,h2,h3,h4,h5,h6,pre,code { font-size:1em; } a img,:link img,:visited img { border:none } body { margin:0 auto; width:770px; font-family: Helvetica, Arial, Sans-serif; font-size:12px; color:#444; }
</style>
</meta>
</head>
<body> 
%(content)s 
</body>
</html>
""" % dict(content = text_html, title = meta["title"])
    with open(os.path.join(g_data.vimpress_temp_dir, "vimpress_temp.html"), 'w') as f:
        f.write(html)
    webbrowser.open("file://%s" % f.name)

def xmlrpc_api_check(func):
    def __check(*args, **kw):
        if not g_data.is_api_ready():
            g_data.blog_update_config()
        return func(*args, **kw)
    return __check

#################################################
# Command Functions
#################################################

@exception_check
@vim_encoding_check
@xmlrpc_api_check
@view_switch(assert_view = "edit", reset = True)
def blog_save(pub = "draft"):
    """
    Saves the current editing buffer.
    @params pub - either "draft" or "publish"
    """
    if pub not in ("publish", "draft"):
        raise VimPressException(":BlogSave draft|publish")

    is_publish = (pub == "publish")

    meta = blog_meta_parse()
    rawtext = '\n'.join(vim.current.buffer[meta["post_begin"]:])

    #Translate markdown and upload as attachment 
    if meta["editformat"].strip().lower() == "markdown":
        attach = blog_upload_markdown_attachment(
                meta["strid"], meta["textattach"], rawtext)
        meta["textattach"] = attach["file"]
        text = markdown.markdown(rawtext.decode('utf-8')).encode('utf-8')

        # Add tag string at the last of the post.
        text += g_data.TAG_STRING % attach
    else:
        text = rawtext

    edit_type = meta["edittype"]
    strid = meta["strid"] 

    if edit_type.lower() not in ("post", "page"):
        raise VimPressException(
                "Fail to work with edit type %s " % edit_type)

    post_struct = dict(title = meta["title"], wp_slug = meta["slug"], 
                    description = text)
    if edit_type == "post":
        post_struct.update(categories = meta["cats"].split(','), 
                        mt_keywords = meta["tags"].split(','))

    # New posts
    if strid == '':
        if edit_type == "post":
            strid = g_data.mw_api.newPost('', g_data.blog_username, g_data.blog_password, 
                    post_struct, is_publish)
        else:
            strid = g_data.wp_api.newPage('', g_data.blog_username, g_data.blog_password, 
                    post_struct, is_publish)

        meta["strid"] = strid

        # update meat area if slug or categories is empty
        if edit_type == "post":
            if meta["slug"] == '' or meta["cats"] == '':
                data = g_data.mw_api.getPost(strid, g_data.blog_username, g_data.blog_password)
                cats = ",".join(data["categories"]).encode("utf-8")
                slug = data["wp_slug"].encode("utf-8")
                meta["cats"] = cats
                meta["slug"] = slug
        else: 
            if meta["slug"] == '':
                data = g_data.wp_api.getPage('', strid, g_data.blog_username, g_data.blog_password)
                slug = data["wp_slug"].encode("utf-8")
                meta["slug"] = slug


        notify = "%s %s.   ID=%s" % \
                (edit_type.capitalize(), 
                        "Published" if is_publish else "Saved as draft", strid)

    # Old posts
    else:
        if edit_type == "post":
            g_data.mw_api.editPost(strid, g_data.blog_username, g_data.blog_password, 
                    post_struct, is_publish)
        elif edit_type == "page":
            g_data.wp_api.editPage('', strid, g_data.blog_username, g_data.blog_password, 
                    post_struct, is_publish)

        notify = "%s edited and %s.   ID=%s" % \
                (edit_type.capitalize(), "published" if is_publish else "saved as a draft", strid)

    blog_meta_area_update(**meta)
    sys.stdout.write(notify)
    vim.command('setl nomodified')

    return meta

@exception_check
@vim_encoding_check
@xmlrpc_api_check
@view_switch(view = "edit")
def blog_new(edit_type = "post", currentContent = None):
    """
    Creates a new editing buffer of specified type.
    @params edit_type - either "post" or "page"
    """
    if edit_type.lower() not in ("post", "page"):
        raise VimPressException("Invalid option: %s " % edit_type)

    blog_wise_open_view()
    meta_dict = dict(edittype = edit_type)
    blog_fill_meta_area(meta_dict)
    vim.current.buffer.append(currentContent)
    vim.current.window.cursor = (1, 0)
    vim.command('setl nomodified')
    vim.command('setl textwidth=0')

@xmlrpc_api_check
@view_switch(view = "edit")
def blog_edit(edit_type, post_id):
    """
    Opens a new editing buffer with blog content of specified type and id.
    @params edit_type - either "post" or "page"
            post_id   - the id of the post or page
    """
    blog_wise_open_view()

    if edit_type.lower() not in ("post", "page"):
        raise VimPressException("Invalid option: %s " % edit_type)

    if edit_type.lower() == "post":
        data = g_data.mw_api.getPost(post_id, g_data.blog_username, g_data.blog_password)
    else: 
        data = g_data.wp_api.getPage('', post_id, g_data.blog_username, g_data.blog_password)

    meta_dict = dict(\
            strid = str(post_id), 
            title = data["title"].encode("utf-8"), 
            slug = data["wp_slug"].encode("utf-8"))
    content = data["description"].encode("utf-8")

    if edit_type.lower() == "post":
        meta_dict["cats"] = ",".join(data["categories"]).encode("utf-8") 
        meta_dict["tags"] = data["mt_keywords"].encode("utf-8")

    meta_dict['editformat'] = "HTML"
    meta_dict['edittype'] = edit_type

    try:
        attach = blog_get_mkd_attachment(content)
        if "mkd_rawtext" in attach:
            meta_dict['editformat'] = "Markdown"
            meta_dict['textattach'] = attach["mkd_name"]
            content = attach["mkd_rawtext"]
    except VimPressFailedGetMkd:
        pass

    blog_fill_meta_area(meta_dict)
    meta = blog_meta_parse()
    vim.current.buffer.append(content.split('\n'))
    vim.current.window.cursor = (meta["post_begin"], 0)
    vim.command('setl nomodified')
    vim.command('setl textwidth=0')

    for v in g_data.LIST_VIEW_KEY_MAP.values():
        if vim.eval("mapcheck('%s')" % v):
            vim.command('unmap <buffer> %s' % v)

@xmlrpc_api_check
@view_switch(assert_view = "list", reset = True)
def blog_delete(edit_type, post_id):
    """
    Deletes a page or post of specified id.
    @params edit_type - either "page" or "post"
            post_id   - the id of the post or page
    """
    if edit_type.lower() not in ("post", "page"):
        raise VimPressException("Invalid option: %s " % edit_type)

    if edit_type.lower() == "post":
        deleted = g_data.mw_api.deletePost('0', post_id, g_data.blog_username, g_data.blog_password, True)
    else:
        deleted = g_data.wp_api.deletePage('', g_data.blog_username, g_data.blog_password, post_id)

    if deleted:
        sys.stdout.write("Deleted %s id %s. \n" % (edit_type, str(post_id)))
    else:
        sys.stdout.write("There was a problem deleting the %s.\n" % edit_type)

    blog_list(edit_type)

@exception_check
@view_switch(assert_view = "list") 
def blog_list_on_key_press(action, edit_type):
    """
    Calls blog open on the current line of a listing buffer.
    """
    if action.lower() not in ("open", "delete"):
        raise VimPressException("Invalid option: %s" % action)

    row = vim.current.window.cursor[0]
    line = vim.current.buffer[row - 1]
    id = line.split()[0]
    title = line[len(id):].strip()

    try:
        int(id)
    except ValueError:
        if line.find("More") != -1:
            if g_data.posts_max != -1:
                sys.stdout.write("No more posts.")
                return
            vim.command("setl modifiable")
            del vim.current.buffer[len(vim.current.buffer) - 1:]
            append_blog_list(edit_type)
            vim.current.buffer.append(g_data.MARKER['more'])
            vim.command("setl nomodified")
            vim.command("setl nomodifiable")
            return
        else:
            raise VimPressException("Move cursor to a post/page line and press Enter.")


    if len(title) > 30:
        title = title[:30] + ' ...'

    if action.lower() == "delete":
        confirm = vim_input("Confirm Delete [%s]: %s? [yes/NO]" % (id,title))
        if confirm != 'yes':
            sys.stdout.write("Delete Aborted.\n")
            return

    vim.command("setl modifiable")
    del vim.current.buffer[:]
    vim.command("setl nomodified")


    if action == "open":
        blog_edit(edit_type, int(id))
    elif action == "delete":
        blog_delete(edit_type, int(id))


def append_blog_list(edit_type, count = g_data.DEFAULT_LIST_COUNT):
    if edit_type.lower() == "post":
        current_posts = len(vim.current.buffer) - 1
        retrive_count = int(count) + current_posts

        g_data.posts_titles = g_data.mw_api.getRecentPosts('', g_data.blog_username, g_data.blog_password, retrive_count)
        len_allposts = len(g_data.posts_titles)
        if len_allposts < current_posts + int(count):
            g_data.posts_max = len_allposts

        vim.current.buffer.append(\
                [(u"%(postid)s\t%(title)s" % p).encode('utf8') for p in g_data.posts_titles[current_posts:]])
    else:
        pages = g_data.wp_api.getPageList('', g_data.blog_username, g_data.blog_password)
        vim.current.buffer.append(\
            [(u"%(page_id)s\t%(page_title)s" % p).encode('utf8') for p in pages])

@exception_check
@vim_encoding_check
@xmlrpc_api_check
@view_switch(view = "list")
def blog_list(edit_type = "post", keep_type = False):
    """
    Creates a listing buffer of specified type.
    @params edit_type - either "post(s)" or "page(s)"
    """
    if keep_type:
        first_line = vim.current.buffer[0]
        re_tag = g_data.MARKER["list_title"].replace('(s)', r'\(s\)') \
                        % dict(edit_type = "(\\S+)", blog_url = ".+")
        result = re.search(re_tag, first_line)
        if result is not None:
            edit_type = result.group(1).lower()

    blog_wise_open_view()
    vim.current.buffer[0] = g_data.MARKER["list_title"] % \
                                dict(edit_type = edit_type.capitalize(), blog_url = g_data.blog_url)

    if edit_type.lower() not in ("post", "page"):
        raise VimPressException("Invalid option: %s " % edit_type)

    append_blog_list(edit_type, g_data.DEFAULT_LIST_COUNT)

    vim.current.buffer.append(g_data.MARKER['more'])

    vim.command("setl nomodified")
    vim.command("setl nomodifiable")
    vim.current.window.cursor = (2, 0)
    vim.command("map <silent> <buffer> %(enter)s :py blog_list_on_key_press('open', '%%s')<cr>" 
            % g_data.LIST_VIEW_KEY_MAP % edit_type)
    vim.command("map <silent> <buffer> %(delete)s :py blog_list_on_key_press('delete', '%%s')<cr>" 
            % g_data.LIST_VIEW_KEY_MAP % edit_type)
    sys.stdout.write("Press <Enter> to edit. <Delete> to move to trash.\n")

@exception_check
@vim_encoding_check
@xmlrpc_api_check
@view_switch(assert_view = "edit")
def blog_upload_media(file_path):
    """
    Uploads a file to the blog.
    @params file_path - the file's path
    """
    if not os.path.exists(file_path):
        raise VimPressException("File does not exist: %s" % file_path)

    name = os.path.basename(file_path)
    filetype = mimetypes.guess_type(file_path)[0]
    with open(file_path) as f:
        bits = xmlrpclib.Binary(f.read())

    result = g_data.mw_api.newMediaObject('', g_data.blog_username, g_data.blog_password, 
            dict(name = name, type = filetype, bits = bits))

    ran = vim.current.range
    if filetype.startswith("image"):
        img = g_data.IMAGE_TEMPLATE % result
        ran.append(img)
    else:
        ran.append(result["url"])
    ran.append('')

@exception_check
@vim_encoding_check
@view_switch(assert_view = "edit")
def blog_append_code(code_type = ""):
    html = \
"""<pre lang="%s"%s>
</pre>"""
    if code_type == "":
        code_type = ("text", "")
    else:
        code_type = (code_type, ' line="1"')
    html = html % code_type
    row, col = vim.current.window.cursor 
    code_block = html.split('\n')
    vim.current.range.append(code_block)
    vim.current.window.cursor = (row + len(code_block), 0)

@exception_check
@vim_encoding_check
@view_switch(assert_view = "edit")
def blog_preview(pub = "local"):
    """
    Opens a browser window displaying the content.
    @params pub - If "local", the content is shown in a browser locally.
                  If "draft", the content is saved as a draft and previewed remotely.
                  If "publish", the content is published and displayed remotely.
    """
    meta = blog_meta_parse()
    rawtext = '\n'.join(vim.current.buffer[meta["post_begin"]:])

    if pub == "local":
        if meta["editformat"].strip().lower() == "markdown":
            html = markdown.markdown(rawtext.decode('utf-8')).encode('utf-8')
            html_preview(html, meta)
        else:
            html_preview(rawtext, meta)
    elif pub == "publish" or pub == "draft":
        meta = blog_save(pub)
        if meta["edittype"] == "page":
            prev_url = "%s?pageid=%s&preview=true" % (g_data.blog_url, meta["strid"])
        else:
            prev_url = "%s?p=%s&preview=true" % (g_data.blog_url, meta["strid"])
        webbrowser.open(prev_url)
        if pub == "draft":
            sys.stdout.write("\nYou have to login in the browser to preview the post when save as draft.")
    else:
        raise VimPressException("Invalid option: %s " % pub)


@exception_check
def blog_guess_open(what):
    """
    Tries several methods to get the post id from different user inputs, such as args, url, postid etc.
    """ 
    post_id = ''
    blog_index = -1
    if type(what) is str:

        for i, p in enumerate(vim.eval("VIMPRESS")):
            if what.startswith(p["blog_url"]):
                blog_index = i

        # User input a url contained in the profiles
        if blog_index != -1:
            guess_id = re.search(r"\S+?p=(\d+)$", what)

            # permantlinks
            if guess_id is None:

                # try again for /archives/%post_id%
                guess_id = re.search(r"\S+/archives/(\d+)", what)

                # fail,  try get full link from headers
                if guess_id is None:
                    headers = urllib.urlopen(what).headers.headers
                    for link in headers:
                        if link.startswith("Link:"):
                            post_id = re.search(r"<\S+?p=(\d+)>", link).group(1)

                    # fail, just give up
                    if post_id == '':
                        raise VimPressException("Failed to get post/page id from '%s'." % what)
                else:
                    post_id = guess_id.group(1)

            # full link with ID (http://blog.url/?p=ID)
            else:
                post_id = guess_id.group(1)

        # Uesr input something not a usabe url, try numberic
        else:
            try:
                post_id = str(int(what))
            except ValueError:
                pass

    # detected something
    if post_id != '':
        if blog_index != -1 and blog_index != g_data.conf_index:
            blog_config_switch(blog_index)
        blog_edit("post", post_id)
    else:
        raise VimPressException("Failed to get post/page id from '%s'." % what)


@vim_encoding_check
@view_switch(reset = True) 
def blog_config_switch(index = -1, refresh_list = False):
    """
    Switches the blog to the next index of the configuration array.
    """
    g_data.config_switch(index)

    if refresh_list:
        blog_list(keep_type = True)

