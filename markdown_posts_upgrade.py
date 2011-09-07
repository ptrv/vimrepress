#!/usr/bin/env python2


import urllib, urllib2, xmlrpclib, sys, re, os, mimetypes, webbrowser, tempfile, time

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
                  list_title = '"====== %(edit_type)s List in %(blog_url)s =========')
    LIST_VIEW_KEY_MAP = dict(enter = "<enter>", delete = "<delete>")
    DEFAULT_META = dict(strid = "", title = "", slug = "", 
                        cats = "", tags = "", editformat = "Markdown", 
                        edittype = "post", textattach = '')
    TAG_STRING = "<!-- #VIMPRESS_TAG# %(url)s %(file)s -->"
    TAG_RE = re.compile(TAG_STRING % dict(url = '(?P<mkd_url>\S+)', file = '(?P<mkd_name>\S+)'))

    #Temp variables.
    __xmlrpc = None
    __conf_index = 0
    __config = None

    view = 'edit'
    vimpress_temp_dir = ''

    blog_username = property(lambda self: self.xmlrpc.username)
    blog_url = property(lambda self: self.xmlrpc.blog_url)
    conf_index = property(lambda self:self.__conf_index)

    xmlrpc = None


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
            raise VimPressFailedGetMkd("Attached markdown not found.")
        attach.update(data.groupdict())
        attach["mkd_rawtext"] = urllib2.urlopen(attach["mkd_url"]).read()
    except (IOError, ValueError):
        raise VimPressFailedGetMkd("The attachment URL was found but was unable to be read.")

    return attach

def blog_update(post, edit_type, new_content, attach):

    markdown_text = attach["mkd_rawtext"]

    content = data["description"]
    if "mt_text_more" in data:
        content += '<!--more-->' + data["mt_text_more"]
    content = content.encode("utf-8")
    lead = content.rindex("<!-- ")
    content = content[:lead]

    is_publish = (post.get(edit_type + "_status") == "publish")

    try:
        strid = post["postid"]
    except KeyError:
        strid = post["page_id"]

    mkd_text_field = dict(key = "mkd_text", value = markdown_text)

    post_struct = dict(post_type = edit_type,
            description = new_content,
            custom_fields = [mkd_text_field]
            )

    if len(post["custom_fields"]) > 0:
        mkd_text_field.update(id = strid)
        

    g_data.xmlrpc.edit_post(strid, post_struct, is_publish)




URL = "http://local.blog"
USER = "admin"
PASS = "123456"

g_data = DataObject()
g_data.xmlrpc = wp_xmlrpc(URL, USER, PASS)

print "Upgrade pages ..."
pages = g_data.xmlrpc.get_page_list()

for page in pages:
    print u"%(page_id)s\t%(page_title)s" % page, '....',
    page_id = page["page_id"].encode("utf-8")
    data = g_data.xmlrpc.get_page(page_id)

    try:
        attach = blog_get_mkd_attachment(content)
    except VimPressFailedGetMkd:
        print "No Markdown Attached."
    else:
        blog_update(data, "page", content, mkd_rawtext)
        print "Updated."



