" Copyright (C) 2007 Adrien Friggeri.
"
" This program is free software; you can redistribute it and/or modify
" it under the terms of the GNU General Public License as published by
" the Free Software Foundation; either version 2, or (at your option)
" any later version.
"
" This program is distributed in the hope that it will be useful,
" but WITHOUT ANY WARRANTY; without even the implied warranty of
" MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
" GNU General Public License for more details.
"
" You should have received a copy of the GNU General Public License
" along with this program; if not, write to the Free Software Foundation,
" Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.  
" 
" Maintainer:	Adrien Friggeri <adrien@friggeri.net>
"               Pigeond <http://pigeond.net/blog/>
"               Preston M.[BOYPT] <pentie@gmail.com>
"               Justin Sattery <justin.slattery@fzysqr.com>
"               Lenin Lee <http://sinolog.it/>
"
" URL:		http://www.friggeri.net/projets/vimblog/
"           http://pigeond.net/blog/2009/05/07/vimpress-again/
"           http://pigeond.net/git/?p=vimpress.git
"           http://apt-blog.net
"           http://fzysqr.com/
"
" VimRepress 
"    - A mod of a mod of a mod of Vimpress.   
"    - A vim plugin fot writting your wordpress blog.
"
" Version:	2.0.0 beta
"
" Configure: Add blog configure into your .vimrc
"
" let VIMPRESS=[{'username':'user',
"               \'password':'pass',
"               \'blog_url':'http://your-first-blog.com/'
"               \},
"               \{'username':'user',
"               \'password':'pass',
"               \'blog_url':'http://your-second-blog.com/'
"               \}]
"
"#######################################################################

if !has("python")
    finish
endif

function! CompSave(ArgLead, CmdLine, CursorPos)
  return "publish\ndraft\n"
endfunction

function! CompPrev(ArgLead, CmdLine, CursorPos)
  return "local\npublish\ndraft\n"
endfunction

function! CompEditType(ArgLead, CmdLine, CursorPos)
  return "post\npage\n"
endfunction

command! -nargs=? -complete=custom,CompEditType BlogNew exec('py blog_new_post(<f-args>)')
command! -nargs=* -complete=custom,CompEditType BlogList exec('py blog_list_posts(<f-args>)')
command! -nargs=? -complete=custom,CompSave BlogSave exec('py blog_send_post(<f-args>)')
command! -nargs=1 BlogOpen exec('py blog_guess_open(<f-args>)')
command! -nargs=1 -complete=file BlogUpload exec('py blog_upload_media(<f-args>)')
command! -nargs=? BlogCode exec('py blog_append_code(<f-args>)')
command! -nargs=? -complete=custom,CompPrev BlogPreview exec('py blog_preview(<f-args>)')
command! -nargs=0 BlogSwitch exec('py blog_config_switch()')

python << EOF
# -*- coding: utf-8 -*-
import urllib , urllib2 , vim , xml.dom.minidom , xmlrpclib , sys , string , re, os, mimetypes, webbrowser, tempfile, time
try:
    import markdown
except ImportError:
    try:
        import markdown2 as markdown
    except ImportError:
        class markdown_stub(object):
            def markdown(self, n):
                raise VimPressException("Your Python didn't have markdown support. Refer :help vimpress for help.")
        markdown = markdown_stub()

image_template = '<a href="%(url)s"><img title="%(file)s" alt="%(file)s" src="%(url)s" class="aligncenter" /></a>'
blog_username = None
blog_password = None
blog_url = None
blog_conf_index = 0
vimpress_view = 'edit'
vimpress_temp_dir = ''

mw_api = None
wp_api = None
marker = ("=========== Meta ============", "=============================", "========== Content ==========")

tag_string = "<!-- #VIMPRESS_TAG# %(url)s %(file)s -->"
tag_re = re.compile(tag_string % dict(url = '(?P<mkd_url>\S+)', file = '(?P<mkd_name>\S+)'))

default_meta = dict(strid = "", title = "", slug = "", 
        cats = "", tags = "", editformat = "Markdown", edittype = "post", textattach = '')

class VimPressException(Exception):
    pass

class VimPressFailedGetMkd(VimPressException):
    pass

def blog_meta_parse():
    """
    parse meta data section in current buffer, return dict.
    """
    meta = dict()
    start = 0
    while not vim.current.buffer[start][1:].startswith(marker[0]):
        start +=1

    end = start + 1
    while not vim.current.buffer[end][1:].startswith(marker[2]):
        if not vim.current.buffer[end].startswith('"===='):
            line = vim.current.buffer[end][1:].strip().split(":")
            k, v = line[0].strip().lower(), ':'.join(line[1:])
            meta[k.strip().lower()] = v.strip()
        end += 1

    meta["post_begin"] = end + 1
    return meta

def blog_meta_area_update(**kw):
    """
    update meta data section with args. only keyword args taken.
    """
    start = 0
    while not vim.current.buffer[start][1:].startswith(marker[0]):
        start +=1

    end = start + 1
    while not vim.current.buffer[end][1:].startswith(marker[2]):
        if not vim.current.buffer[end].startswith('"===='):
            line = vim.current.buffer[end][1:].strip().split(":")
            k, v = line[0].strip().lower(), ':'.join(line[1:])
            if k in kw:
                new_line = "\"%s: %s" % (line[0], kw[k])
                vim.current.buffer[end] = new_line
        end += 1

def blog_fill_meta_area(meta):
    """
    Fill in a meta data section in current buffer, with a meta dict, and edit_type in "post" and "page"
    """
    for k in default_meta.keys():
        if k not in meta:
            meta[k] = default_meta[k]

    meta.update(dict(bg = marker[0], mid = marker[1], ed = marker[2]))
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
        raise VimPressException("Fail to work with edit type %(edittype)s " % meta)
    meta_text = template[meta["edittype"].lower()] % meta
    meta = meta_text.split('\n')
    vim.current.buffer[0] = meta[0]
    vim.current.buffer.append(meta[1:])

def blog_get_mkd_attachment(post):
    """
    Find the vimpress tag in the post content. And parse for the attachment url, then return a dict with attached markdown file content and its url.
    """

    attach = dict()
    try:
        lead = post.rindex("<!-- ")
        data = re.search(tag_re, post[lead:])
        if data is None:
            raise ValueError()
        attach.update(data.groupdict())
        attach["mkd_rawtext"] = urllib2.urlopen(attach["mkd_url"]).read()
    except ValueError, e:
        return dict()
    except IOError:
        raise VimPressFailedGetMkd("Attachment url found but fail to get markdown text.")

    return attach

def blog_upload_markdown_attachment(post_id, attach_name, mkd_rawtext):
    bits = xmlrpclib.Binary(mkd_rawtext)

    # New Post, new file
    if post_id == '' or attach_name == '':
        attach_name = "vimpress_%s_mkd.txt" % hex(int(time.time()))[2:]
        overwrite = False
    else:
        overwrite = True

    sys.stdout.write("Markdown File Uploading ... ")
    result = mw_api.newMediaObject(1, blog_username, blog_password, 
                dict(name = attach_name, 
                    type = "text/plain", bits = bits, 
                    overwrite = overwrite))
    sys.stdout.write("%s\n" % result["file"])
    return result

def __exception_check(func):
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

def __vim_encoding_check(func):
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

def __xmlrpc_api_check(func):
    def __check(*args, **kw):
        if wp_api is None or mw_api is None:
            raise VimPressException("Please at lease add a blog config in your .vimrc .")
        return func(*args, **kw)
    return __check

@__exception_check
@__vim_encoding_check
@__xmlrpc_api_check
def blog_send_post(pub = "publish"):
    if vimpress_view != 'edit':
        raise VimPressException("Command not available at list view")
    if pub not in ("publish", "draft"):
        raise VimPressException(":BlogSave draft|publish")

    is_publish = (pub == "publish")

    meta = blog_meta_parse()
    rawtext = '\n'.join(vim.current.buffer[meta["post_begin"]:])

    #Translate markdown and upload as attachment 
    if meta["editformat"].strip().lower() == "markdown":
        attach = blog_upload_markdown_attachment(
                meta["strid"], meta["textattach"], rawtext)
        blog_meta_area_update(textattach = attach["file"])
        text = markdown.markdown(rawtext.decode('utf-8')).encode('utf-8')

        # Add tag string at the last of the post.
        text += tag_string % attach
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
                        mt_keywords = meta["tags"])

    # New posts
    if strid == '':
        if edit_type == "post":
            strid = mw_api.newPost('', blog_username, blog_password, 
                    post_struct, is_publish)
        elif edit_type == "page":
            strid = wp_api.newPage('', blog_username, blog_password, 
                    post_struct, is_publish)

        blog_meta_area_update(strid = strid)
        meta["strid"] = strid

        notify = "%s %s.   ID=%s" % \
                (edit_type.capitalize(), 
                        "Published" if is_publish else "Saved as draft", strid)

    # Old posts
    else:
        if edit_type == "post":
            mw_api.editPost(strid, blog_username, blog_password, 
                    post_struct, is_publish)
        elif edit_type == "page":
            wp_api.editPage('', strid, blog_username, blog_password, 
                    post_struct, is_publish)

        notify = "%s Edited. %s.   ID=%s" % \
                (edit_type.capitalize(), "Published" if is_publish else "Saved", strid)

    sys.stdout.write(notify)
    vim.command('setl nomodified')

    return meta

@__exception_check
@__vim_encoding_check
def blog_new_post(edit_type = "post"):
    global vimpress_view

    if edit_type.lower() not in ("post", "page"):
        raise VimPressException("Fail to work with edit type %s " % edit_type)

    if vimpress_view.startswith("list"):
        currentContent = ['']
        if vim.eval("mapcheck('<enter>')"):
            vim.command('unmap <buffer> <enter>')
    else:
        currentContent = vim.current.buffer[:]

    blog_wise_open_view()
    vimpress_view = 'edit'
    vim.command("setl syntax=blogsyntax")

    meta_dict = dict()

    if edit_type.lower() == "post":
        cat_info = mw_api.getCategories('', blog_username, blog_password)
        meta_dict["cats"] = ", ".join([i["description"].encode("utf-8")
                        for i in cat_info])

    meta_dict["edittype"] = edit_type
    blog_fill_meta_area(meta_dict)

    vim.current.buffer.append(currentContent)
    vim.current.window.cursor = (1, 0)
    vim.command('setl nomodified')
    vim.command('setl textwidth=0')


def blog_open_post(edit_type, post_id):
    global vimpress_view
    vimpress_view = 'edit'

    blog_wise_open_view()
    vim.command("setl syntax=blogsyntax")

    if edit_type.lower() not in ("post", "page"):
        raise VimPressException("Fail to work with edit type %s " % edit_type)

    if edit_type.lower() == "post":
        data = mw_api.getPost(post_id, blog_username, blog_password)
    else: 
        data = wp_api.getPage('', post_id, blog_username, blog_password)

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

    if vim.eval("mapcheck('<enter>')"):
        vim.command('unmap <buffer> <enter>')

def blog_list_edit():
    global vimpress_view
    row = vim.current.window.cursor[0]
    id = vim.current.buffer[row - 1].split()[0]
    vim.command("setl modifiable")
    del vim.current.buffer[:]
    vim.command("setl nomodified")

    if vimpress_view == 'list_page':
        edit_type = 'page'
    elif vimpress_view == 'list_post':
        edit_type = 'post'
    else:
        raise VimPressException("Don't know what to edit : %s" % vimpress_view)

    blog_open_post(edit_type, int(id))

@__exception_check
@__vim_encoding_check
@__xmlrpc_api_check
def blog_list_posts(edit_type = "post", count = "30"):

    global vimpress_view
    vimpress_view = 'list'

    blog_wise_open_view()
    vim.command("setl syntax=blogsyntax")
    vim.current.buffer[0] = "\"====== List of %ss in %s =========" % (edit_type.capitalize(), blog_url)

    if edit_type.lower() not in ("post", "page"):
        raise VimPressException("Fail to work with edit type %s " % edit_type)

    if edit_type.lower() == "post":
        vimpress_view = 'list_post'
        allposts = mw_api.getRecentPosts('',blog_username, blog_password, int(count))
        vim.current.buffer.append(\
            [(u"%(postid)s\t%(title)s" % p).encode('utf8') for p in allposts])
    elif edit_type.lower() == "page":
        vimpress_view = 'list_page'
        pages = wp_api.getPageList('', blog_username, blog_password)
        vim.current.buffer.append(\
            [(u"%(page_id)s\t%(page_title)s" % p).encode('utf8') for p in pages])

    vim.command('setl nomodified')
    vim.command("setl nomodifiable")
    vim.current.window.cursor = (2, 0)
    vim.command('map <buffer> <enter> :py blog_list_edit()<cr>')

@__exception_check
@__vim_encoding_check
@__xmlrpc_api_check
def blog_upload_media(file_path):
    if vimpress_view != 'edit':
        raise VimPressException("Command not available at list view")
    if not os.path.exists(file_path):
        raise VimPressException("File does not exist: %s" % file_path)

    name = os.path.basename(file_path)
    filetype = mimetypes.guess_type(file_path)[0]
    with open(file_path) as f:
        bits = xmlrpclib.Binary(f.read())

    result = mw_api.newMediaObject('', blog_username, blog_password, 
            dict(name = name, type = filetype, bits = bits))

    ran = vim.current.range
    if filetype.startswith("image"):
        img = image_template % result
        ran.append(img)
    else:
        ran.append(result["url"])
    ran.append('')

@__exception_check
@__vim_encoding_check
def blog_append_code(code_type = ""):
    if vimpress_view != 'edit':
        raise VimPressException("Command not available at list view")
    html = \
"""<pre escaped="True"%s>
</pre>"""
    if code_type != "":
        args = ' lang="%s" line="1"' % code_type
    else:
        args = ''

    row, col = vim.current.window.cursor 
    code_block = (html % args).split('\n')
    vim.current.range.append(code_block)
    vim.current.window.cursor = (row + len(code_block), 0)

@__exception_check
@__vim_encoding_check
def blog_preview(pub = "local"):
    if vimpress_view != 'edit':
        raise VimPressException("Command not available at list view")
    meta = blog_meta_parse()
    rawtext = '\n'.join(vim.current.buffer[meta["post_begin"]:])

    if pub == "local":
        if meta["editformat"].strip().lower() == "markdown":
            html = markdown.markdown(rawtext.decode('utf-8')).encode('utf-8')
            html_preview(html, meta)
        else:
            html_preview(rawtext, meta)
    elif pub == "publish" or pub == "draft":
        meta = blog_send_post(pub)
        if meta["edittype"] == "page":
            prev_url = "%s?pageid=%s&preview=true" % (blog_url, meta["strid"])
        else:
            prev_url = "%s?p=%s&preview=true" % (blog_url, meta["strid"])
        webbrowser.open(prev_url)
        if pub == "draft":
            sys.stdout.write("\nYou have to login in the browser to preview the post when save as draft.")
    else:
        raise VimPressException("Don't know what to do: %s" % pub)


@__exception_check
def blog_guess_open(what):
    """ Try for some methods to get the post id from anything user inputs as args, url, postid etc.  """ 
    post_id = ''
    if type(what) is str:
        if what.startswith(blog_url):
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
                        raise VimPressException("Failed to get post id from: %s " % what)
                else:
                    post_id = guess_id.group(1)

            # full link with ID (http://blog.url/?p=ID)
            else:
                post_id = guess_id.group(1)

        else:
            try:
                post_id = str(int(what))
            except ValueError:
                pass

    if post_id != '':
        blog_open_post("post", post_id)
    else:
        raise VimPressException("Failed to get post id from: %s " % what)


@__exception_check
def blog_update_config(wp_config):
    global blog_username, blog_password, blog_url, mw_api, wp_api
    try:
        blog_username = wp_config['username']
        blog_password = wp_config['password']
        blog_url = wp_config['blog_url']
        mw_api = xmlrpclib.ServerProxy("%s/xmlrpc.php" % blog_url).metaWeblog
        wp_api = xmlrpclib.ServerProxy("%s/xmlrpc.php" % blog_url).wp
    except vim.error:
        raise VimPressException("No Wordpress configured for Vimpress.")
    except KeyError, e:
        raise VimPressException("Configure Error: %s" % e)

@__exception_check
@__vim_encoding_check
def blog_config_switch():
    global blog_conf_index
    try:
        blog_conf_index += 1
        wp = vim.eval("VIMPRESS")[blog_conf_index]
    except IndexError:
        blog_conf_index = 0
        wp = vim.eval("VIMPRESS")[blog_conf_index]

    blog_update_config(wp)
    if vimpress_view.startswith('list'):
        blog_list_posts()
    sys.stdout.write("Vimpress switched to %s" % blog_url)

def html_preview(text_html, meta):
    global vimpress_temp_dir
    if vimpress_temp_dir == '':
        vimpress_temp_dir = tempfile.mkdtemp(suffix="vimpress")
    
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
    with open(os.path.join(vimpress_temp_dir, "vimpress_temp.html"), 'w') as f:
        f.write(html)
    webbrowser.open("file://%s" % f.name)

def blog_wise_open_view():
    '''Wisely decide whether to wipe out the content of current buffer 
    or to open a new splited window.
    '''
    if vim.current.buffer.name is None and \
            (vim.eval('&modified') == '0' or \
                len(vim.current.buffer) == 1):
        vim.command('setl modifiable')
        del vim.current.buffer[:]
        vim.command('setl nomodified')
    else:
        vim.command(":new")

if __name__ == "__main__":
    try:
        if vim.eval('exists("VIMPRESS")') != '1':
            raise VimPressException()
        wp = vim.eval("VIMPRESS")[0]
    except VimPressException:
        pass
    except IndexError:
        sys.stderr.write("Vimpress default configure index error. Check your .vimrc and review :help vimpress ")
    else:    
        blog_update_config(wp)

