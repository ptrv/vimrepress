# -*- coding: utf-8 -*-
import urllib, urllib2, vim, xmlrpclib, sys, re, os, mimetypes, webbrowser, tempfile, time
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
        except (VimPressException, AssertionError), e:
            sys.stderr.write(str(e))
        except (xmlrpclib.Fault, xmlrpclib.ProtocolError), e:
            sys.stderr.write("xmlrpc error: %s" % e.faultString.encode("utf-8"))
        except IOError, e:
            sys.stderr.write("network error: %s" % e)

    return __check

#################################################
# Helper Classes
#################################################

class VimPressException(Exception):
    pass

class DataObject(object):

    #CONST
    DEFAULT_LIST_COUNT = "15"
    IMAGE_TEMPLATE = '<a href="%(url)s"><img title="%(file)s" alt="%(file)s" src="%(url)s" class="aligncenter" /></a>'
    MARKER = dict(bg = "=========== Meta ============", 
                  mid = "=============================", 
                  ed = "========== Content ==========",
                  more = '"====== Press Here for More ======',
                  list_title = '"====== %(edit_type)s List in %(blog_url)s =========')
    LIST_VIEW_KEY_MAP = dict(enter = "<enter>", delete = "<delete>")
    DEFAULT_META = dict(strid = "", title = "", slug = "", 
                        cats = "", tags = "", editformat = "Markdown", 
                        edittype = "post") 
    CUSTOM_FIELD_KEY = "mkd_text"

    #Temp variables.
    __xmlrpc = None
    __conf_index = 0
    __config = None

    view = 'edit'
    vimpress_temp_dir = ''

    blog_username = property(lambda self: self.xmlrpc.username)
    blog_url = property(lambda self: self.xmlrpc.blog_url)
    conf_index = property(lambda self:self.__conf_index)

    @conf_index.setter
    def conf_index(self, index):
        try:
            index = int(index)
        except ValueError:
            raise VimPressException("Invalid Index: %s" % index)

         #auto increase
        if index < 0:
            self.__conf_index += 1
            if self.__conf_index >= len(self.config):
                self.__conf_index = 0
         # user enter index
        else:
            assert index < len(self.config), "Invalid Index: %d" % index
            self.__conf_index = index

        self.__xmlrpc = None


    @property
    def xmlrpc(self):
        if self.__xmlrpc is None:
            conf_index = self.conf_index
            config = self.config[conf_index]

            if "xmlrpc_obj" not in config:
                try:
                    blog_username = config['username']
                    blog_password = config.get('password', '')
                    blog_url = config['blog_url']
                except KeyError, e:
                    raise VimPressException("Configuration error: %s" % e)
                sys.stdout.write("Connecting to '%s' ... " % blog_url)
                if blog_password == '':
                   blog_password = vim_input("Enter password for %s" % blog_url, True)
                config["xmlrpc_obj"] = wp_xmlrpc(blog_url, blog_username, blog_password)

            self.__xmlrpc = config["xmlrpc_obj"]

            # Setting tags and categories for completefunc
            categories = config.get("categories", None)
            if categories is None:
                categories = [i["description"].encode("utf-8") for i in self.xmlrpc.get_categories()]
                config["categories"] = categories

            vim.command('let s:completable = "%s"' % '|'.join(categories))
            sys.stdout.write("done.\n")
        return self.__xmlrpc

    @property
    def config(self):
        if self.__config is None:
            try:
                self.__config = vim.eval("VIMPRESS")
            except vim.error:
                raise VimPressException("Could not find vimpress configuration. Please read ':help vimpress' for more information.")
        return self.__config

class wp_xmlrpc(object):

    def __init__(self, blog_url, username, password):
        self.blog_url = blog_url
        self.username = username
        self.password = password
        p = xmlrpclib.ServerProxy(os.path.join(blog_url, "xmlrpc.php"))
        self.mw_api = p.metaWeblog
        self.wp_api = p.wp
        self.mt_api = p.mt
        self.demo_api = p.demo

        assert self.demo_api.sayHello() == "Hello!", "XMLRPC Error with communication with '%s'@'%s'" % \
                (username, blog_url)

        self.cache_reset()

    def cache_reset(self):
        self.__cache_post_titles = []
        self.__post_title_max = False

    def cache_remove_post(self, postid):
        for p in self.__cache_post_titles:
            if p["postid"] == str(postid):
                self.__cache_post_titles.remove(p)
                break

    is_reached_title_max = property(lambda self: self.__post_title_max)

    new_post = lambda self, post_struct, is_publish: self.mw_api.newPost('',
            self.username, self.password, post_struct, is_publish)

    get_post = lambda self, post_id: self.mw_api.getPost(post_id,
            self.username, self.password) 

    edit_post = lambda self, post_id, post_struct, is_publish: self.mw_api.editPost(post_id,
            self.username, self.password, post_struct, is_publish)

    delete_post = lambda self, post_id: self.mw_api.deletePost('', post_id, self.username,
            self.password, '') 

    def get_recent_post_titles(self, retrive_count = 0):
        if retrive_count > len(self.__cache_post_titles) and not self.is_reached_title_max:
            self.__cache_post_titles = self.mt_api.getRecentPostTitles('',
                    self.username, self.password, retrive_count)
            if len(self.__cache_post_titles) < retrive_count:
                self.__post_title_max = True

        return self.__cache_post_titles

    get_categories = lambda self:self.mw_api.getCategories('', self.username, self.password)

    new_media_object = lambda self, object_struct: self.mw_api.newMediaObject('', self.username,
            self.password, object_struct)

    get_page = lambda self, page_id: self.wp_api.getPage('', page_id, self.username, self.password) 

    delete_page = lambda self, page_id: self.wp_api.deletePage('',
            self.username, self.password, page_id) 

    get_page_list = lambda self: self.wp_api.getPageList('', self.username, self.password) 

#################################################
# Golbal Variables
#################################################
g_data = DataObject()

#################################################
# Helper Functions
#################################################

def vim_encoding_check(func):
    """
    Decorator.
    Check vim environment. wordpress via xmlrpc only support unicode data, setting vim
        to utf-8 for all data compatible.
    """
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
    """
    Decorator.
    For commands to switch between edit/list view, data/status need to be configured.
    """
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
                g_data.xmlrpc.cache_reset()

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
"%(ed)s""", 
        page = \
""""%(bg)s
"StrID : %(strid)s
"Title : %(title)s
"Slug  : %(slug)s
"%(mid)s
"EditType   : %(edittype)s
"EditFormat : %(editformat)s
"%(ed)s""") 

    if meta["edittype"] not in ("post", "page"):
        raise VimPressException("Invalid option: %(edittype)s " % meta)
    meta_text = template[meta["edittype"].lower()] % meta
    meta = meta_text.split('\n')
    vim.current.buffer[0] = meta[0]
    vim.current.buffer.append(meta[1:])

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


#################################################
# Command Functions
#################################################

@exception_check
@vim_encoding_check
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
    strid = meta["strid"] 
    edit_type = meta["edittype"]
    if edit_type.lower() not in ("post", "page"):
        raise VimPressException(
                "Fail to work with edit type %s " % edit_type)

    post_struct = dict(title = meta["title"], wp_slug = meta["slug"], post_type = edit_type)
    mkd_text_field = {}

    #Translate markdown and save in custom fields.
    if meta["editformat"].strip().lower() == "markdown":
        post_struct["description"] = markdown.markdown(rawtext.decode('utf-8')).encode('utf-8')
        mkd_text_field.update(key = g_data.CUSTOM_FIELD_KEY, value = rawtext)
        post_struct["custom_fields"] = [mkd_text_field]
    else:
        post_struct["description"] = rawtext

    if edit_type == "post":
        post_struct.update(categories = meta["cats"].split(','), 
                        mt_keywords = meta["tags"].split(','))

    # New posts
    if strid == '':
        strid = g_data.xmlrpc.new_post(post_struct, is_publish)

        meta["strid"] = strid

        # update meat area if slug or categories is empty
        if edit_type == "post":
            if meta["slug"] == '' or meta["cats"] == '':
                data = g_data.xmlrpc.get_post(strid)
                cats = ",".join(data["categories"]).encode("utf-8")
                slug = data["wp_slug"].encode("utf-8")
                meta["cats"] = cats
                meta["slug"] = slug
        else: 
            if meta["slug"] == '':
                data = g_data.xmlrpc.get_page(strid)
                slug = data["wp_slug"].encode("utf-8")
                meta["slug"] = slug


        notify = "%s %s.   ID=%s" % \
                (edit_type.capitalize(), 
                        "Published" if is_publish else "Saved as draft", strid)

    # Old posts
    else:
        if mkd_text_field.has_key("key"):
            mkd_text_field["id"] = strid
        g_data.xmlrpc.edit_post(strid, post_struct, is_publish)

        notify = "%s edited and %s.   ID=%s" % \
                (edit_type.capitalize(), "published" if is_publish else "saved as a draft", strid)

    blog_meta_area_update(**meta)
    sys.stdout.write(notify)
    vim.command('setl nomodified')

    return meta

@exception_check
@vim_encoding_check
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
        data = g_data.xmlrpc.get_post(post_id)
    else: 
        data = g_data.xmlrpc.get_page(post_id)

    meta_dict = dict(\
            strid = str(post_id), 
            title = data["title"].encode("utf-8"), 
            slug = data["wp_slug"].encode("utf-8"))
    content = data["description"]
    if "mt_text_more" in data:
        content += '<!--more-->' + data["mt_text_more"]
    content = content.encode("utf-8")

    if edit_type.lower() == "post":
        meta_dict["cats"] = ",".join(data["categories"]).encode("utf-8") 
        meta_dict["tags"] = data["mt_keywords"].encode("utf-8")

    meta_dict['editformat'] = "HTML"
    meta_dict['edittype'] = edit_type

    for field in data["custom_fields"]:
        if field["key"] == g_data.CUSTOM_FIELD_KEY:
            meta_dict['editformat'] = "Markdown"
            content = field["value"]
            break

    blog_fill_meta_area(meta_dict)
    meta = blog_meta_parse()
    vim.current.buffer.append(content.split('\n'))
    vim.current.window.cursor = (meta["post_begin"], 0)
    vim.command('setl nomodified')
    vim.command('setl textwidth=0')

    for v in g_data.LIST_VIEW_KEY_MAP.values():
        if vim.eval("mapcheck('%s')" % v):
            vim.command('unmap <buffer> %s' % v)

@view_switch(assert_view = "list")
def blog_delete(edit_type, post_id):
    """
    Deletes a page or post of specified id.
    @params edit_type - either "page" or "post"
            post_id   - the id of the post or page
    """
    if edit_type.lower() not in ("post", "page"):
        raise VimPressException("Invalid option: %s " % edit_type)
    deleted = getattr(g_data.xmlrpc, "delete_" + edit_type)(post_id)
    assert deleted is True, "There was a problem deleting the %s.\n" % edit_type
    sys.stdout.write("Deleted %s id %s. \n" % (edit_type, str(post_id)))
    g_data.xmlrpc.cache_remove_post(post_id)
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
            assert g_data.xmlrpc.is_reached_title_max is False, "No more posts."
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
        assert confirm.lower() == 'yes', "Delete Aborted."

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
        posts_titles = g_data.xmlrpc.get_recent_post_titles(retrive_count)

        vim.current.buffer.append(\
                [(u"%(postid)s\t%(title)s" % p).encode('utf8') for p in posts_titles[current_posts:]])
    else:
        pages = g_data.xmlrpc.get_page_list()
        vim.current.buffer.append(\
            [(u"%(page_id)s\t%(page_title)s" % p).encode('utf8') for p in pages])

@exception_check
@vim_encoding_check
@view_switch(view = "list")
def blog_list(edit_type = "post", keep_type = False):
    """
    Creates a listing buffer of specified type.
    @params edit_type - either "post(s)" or "page(s)"
    """
    if keep_type:
        first_line = vim.current.buffer[0]
        assert first_line.find("List") != -1,"Failed to detect current list type."
        edit_type = first_line.split()[1].lower()

    blog_wise_open_view()
    vim.current.buffer[0] = g_data.MARKER["list_title"] % \
                                dict(edit_type = edit_type.capitalize(), blog_url = g_data.blog_url)

    if edit_type.lower() not in ("post", "page"):
        raise VimPressException("Invalid option: %s " % edit_type)

    append_blog_list(edit_type, g_data.DEFAULT_LIST_COUNT)

    if edit_type == "post":
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

    result = g_data.xmlrpc.new_media_object(dict(name = name, type = filetype, bits = bits))

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
    elif pub in ("publish", "draft"):
        meta = blog_save(pub)
        webbrowser.open("%s?p=%s&preview=true" % (g_data.blog_url, meta["strid"]))
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

                else:
                    post_id = guess_id.group(1)

            # full link with ID (http://blog.url/?p=ID)
            else:
                post_id = guess_id.group(1)

            # detected something ?
            assert post_id != '', "Failed to get post/page id from '%s'." % what

             #switch view if needed.
            if blog_index != -1 and blog_index != g_data.conf_index:
                blog_config_switch(blog_index)

        # Uesr input something not a usabe url, try numberic
        else:
            try:
                post_id = str(int(what))
            except ValueError:
                raise VimPressException("Failed to get post/page id from '%s'." % what)

        blog_edit("post", post_id)

@exception_check
@vim_encoding_check
@view_switch()
def blog_config_switch(index = -1, refresh_list = False):
    """
    Switches the blog to the 'index' of the configuration array.
    """
    g_data.conf_index = index
    if refresh_list:
        blog_list(keep_type = True)
    sys.stdout.write("Vimpress switched to '%s'@'%s'\n" % (g_data.blog_username, g_data.blog_url))

