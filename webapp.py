#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = "Vladimir Korshunov <v.korshunov@wwpass.com>"
__author__ = "Rostislav Kondratenko <r.kondratenko@wwpass.com>"
__copyright__ = "WWPass Corporation, 2012"
__version__ = "1.0.0"

# WebApp
import sys
import os
import locale
import logging
import httplib
import traceback
import tornado
import tornado.httpserver
import tornado.ioloop
import tornado.web
import tornado.httpclient
from tornado.options import define, parse_config_file, parse_command_line, options

import datetime

# Storage
import pymongo

import re
from urllib import quote

from bs4 import *
from bs4 import Tag
# TODO
# @todo

class AlibRecord(object):
    def __init__(self,tag):
        b = tag.next
        if not isinstance(b,Tag):
            raise TypeError('Wrong tag for AlibRecord')
        self.title = b.get_text()
        self.description = tag.__str__()
        a = tag.find_all('a', href=re.compile(r'alib\.ru/\w+\.html$'))
        if len(a) != 1:
            raise TypeError('Wrong tag for AlibRecord')
        a = a[0]
        self.link = a.attrs['href']
        i = db.items.find_one({'link':self.link})
        if not i:
            self.time = datetime.utcnow()
            db.items.insert({
                'link':self.link,
                'text':self.description,
                'time':self.time,
                'title':self.title
                })
        else:
            self.time = i['time']

class ErrorHandler(tornado.web.RequestHandler):
    def __init__(self, application, request, status_code):
        tornado.web.RequestHandler.__init__(self, application, request)
        self.set_status(status_code)

    def get_error_html(self, status_code, **kwargs):
        if status_code == 404:
            # return tornado.template.Loader(os.path.join(base_path, options.templates_path)).load('page.html').generate()
            return

        errorTraceback = repr(self.request)

        if "exc_info" in kwargs:
            for line in traceback.format_exception(*kwargs["exc_info"]):
                errorTraceback += line

        logging.exception(errorTraceback)

        if options.debug:
            self.set_header('Content-Type', 'text/plain')
            return "Status %(code)d: %(message)s\n%(error)s\n"% {
                "code": status_code,
                "message": httplib.responses[status_code],
                "error": errorTraceback
                }
        else:
            return


class BaseHandler(tornado.web.RequestHandler):
    def __init__(self, application, request, **kwargs):
        tornado.web.RequestHandler.__init__(self, application, request, **kwargs)
        self._user = None

    def render(self, template_name, **kwargs):
        super(BaseHandler, self).render(
            template_name,
            debug=options.debug,
            current_user=self.get_current_user(),
            **kwargs
            )

class Home(BaseHandler):
    def get(self):
        self.render('home.html')

class RSS(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        http_client = tornado.httpclient.AsyncHTTPClient()
        author = self.get_argument('author','')
        title = self.get_argument('title','')
        y1 = self.get_argument('y1','')
        y2 = self.get_argument('y2','')
        query_string="author=+%s&title=+%s&seria=+&izdat=&isbnp=&god1=%s&god2=%s&cena1=&cena2=&sod=&bsonly=&lday=&minus=+&tipfind=&sortby=8&Bo1=%%CD%%E0%%E9%%F2%%E8"\
            % (quote(author.encode("cp1251")),quote(title.encode("cp1251")),quote(y1.encode("cp1251")),quote(y2.encode("cp1251")))
        self.title = "Alib — %s/%s" % (author,title)
        logging.debug('Fetching %s',query_string)
        http_client.fetch("http://www.alib.ru/findp.php4?"+query_string, self.handle_response)

    @tornado.web.asynchronous
    def handle_response(self,response):
        if response.error:
            logging.error(response.error)
            self.set_status(response.code)
            self.finish()
        else:
            try:
                s = BeautifulSoup(response.body,'lxml')
                def p_aftertable(tag):
                    return tag.name=='p' and hasattr(tag.previousSibling,'name') and tag.previousSibling.name=='hr'
                pt = s.body.find_all(p_aftertable)
                items = []
                if pt:
                    pt=pt[0]
                    while True:
                        try:
                            items.append(AlibRecord(p))
                        except:
                            pass
                        pt = pt.nextSibling
                        if not p:
                            break
                        pt = pt.nextSibling
                        if not pt:
                            break
            except:
                logging.exception("Parsing error:")
                self.set_status(500)
                self.finish()
                return
            self.set_header("Content-Type", "application/rss+xml; charset=UTF-8")
            self.render('rss.xml',query_string = self.request.query, title=self.title, items=items)

def ensure_indexes(database):
    database.items.ensure_index('link',unique=True)
    database.items.ensure_index('time')

def setup_uid(user, group, logfile):
    assert os.getuid() == 0
    if unicode(user).isdecimal():
        uid = int(user)
    else:
        import pwd
        uid = pwd.getpwnam(user)[2]
    if unicode(group).isdecimal():
        gid = int(group)
    else:
        import grp
        gid = grp.getgrnam(user)[2]
    assert uid != 0 and gid != 0
    if logfile:
        os.chown(logfile, uid, gid)
    os.setgid(gid)
    os.setuid(uid)

class Validate(BaseHandler):
    def get(self):
        self.write('4e75e424876ee4d2a926221cbdd98954b0fb3f6d')

if __name__ == "__main__":
    urls = [
        ("/", Home),
        ("/rss", RSS),
        ("/1178e006e3d3a607fa8c982bd218a48d.txt", Validate),
    ]

    define("debug", type=bool, default=False)
    define("user",default='')
    define("group",default='')
    define("domain")
    define("bind_host")
    define("bind_port", type=int)
    define("locale", default="en_US")
    define("templates_path", default="templates")
    define("mongo_hosts", type=list, default=["127.0.0.1:27017"])
    define("mongo_db")

    parse_config_file(sys.argv[1])
    parse_command_line()

    locale.setlocale(locale.LC_ALL, "%s.UTF-8" % options.locale)
    reload(sys)
    sys.setdefaultencoding('utf-8')

    settings = dict(
        debug=options.debug,
        template_path=options.templates_path,
        autoescape=None,
        cookie_secret="i4KbrDYElSYYqoTUD8v3IzLh/s6c/F7QkaIusLyrIoU="
    )

    tornado.web.ErrorHandler = ErrorHandler

    for host in options.mongo_hosts:
        try:
            h,p = host.split(':')
            mongo = pymongo.MongoClient(h,int(p))
            logging.info("Connected to Mongo host: %s",host)
            break
        except:
            logging.exception("Cannot connect to Mongo host: %s",host)
    else:
        logging.error("Cannot connect to Mongo")

    db = getattr(mongo,options.mongo_db)
    ensure_indexes(db)

    http_server = tornado.httpserver.HTTPServer(tornado.web.Application(urls, **settings), xheaders=True)
    http_server.listen(options.bind_port, options.bind_host)
    logging.info("Server version %s binded to %s:%d", __version__, options.bind_host, options.bind_port)
    if options.user and options.group: setup_uid(options.user, options.group, options.log_file_prefix)
    tornado.ioloop.IOLoop.instance().start()
