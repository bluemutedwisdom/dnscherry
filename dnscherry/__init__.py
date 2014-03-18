#!/usr/bin/env python
# -*- coding: utf-8 -*-

import dns.query
import dns.zone
import dns.tsigkeyring
from dns.tsig import PeerBadKey
import dns.update
from operator import itemgetter
from dns.exception import DNSException
from dns.rdataclass import *
from dns.rdatatype import *
import sys

import cherrypy
from cherrypy.lib.httputil import parse_query_string
from mako.template import Template
from mako import lookup

resource_dir = '/home/kakwa/Geek/GitHub/dnscherry/resources/static/'
template_dir = '/home/kakwa/Geek/GitHub/dnscherry/resources/templates/'
zone_list = {'example.com': {'ip': '127.0.0.1', 'key': 'ujeGPu0NCU1TO9fQKiiuXg==', 'algorithm': 'hmac-md5'},
        }
zone_default2 = 'example.com'
type_displayed = [ 'A', 'AAAA', 'CNAME']
type_written = [ 'A', 'AAAA', 'CNAME', 'MX', 'CACA']
default_ttl = '3600'

class DnsCherry(object):

    def __init__(self):
        # definition of resource directory (css, js, img...)
        self.resource_dir = resource_dir
        # definition of the template directory
        self.template_dir = template_dir
        # recovery of zones list (zones dnscherry will manage)
        self.zone_list = zone_list
        # configure the default zone (zone displayed by default)
        self.zone_default = zone_default2
        # configure the default ttl for the form
        self.default_ttl = default_ttl
        # configure the list of dns entry type to display
        self.type_displayed = type_displayed
        # configure the list of dns entry type a user can write
        self.type_written = type_written
        # preload templates
        self.temp_lookup = lookup.TemplateLookup(directories=self.template_dir, input_encoding='utf-8')
        self.temp_index = self.temp_lookup.get_template('index.tmpl')

        # enable serving static content threw cherrypy
        static_handler = cherrypy.tools.staticdir.handler(section="/", 
                dir=resource_dir)
        cherrypy.tree.mount(static_handler, '/static/')

    def _refresh_zone(self, zone = None):
        """get the dns zone 'zone'.
           It only lists records which type are in 'self.type_written'.
           'zone' must be correctly configured in 'self.zone_list'

           @str zone: the zone name to refresh
           @rtype: list of hash {'key', 'class', 'type', 'ttl', 'content'}
        """
        # zone is defined by the query string parameter
        # if query string is empty, use the default zone
        if zone is None:
            zone = self.zone_default
        # get the zone from the dns
        self.zone = dns.zone.from_xfr(dns.query.xfr(
            self.zone_list[zone]['ip'], zone))
        records = []
        # get all the records in a list of hash 
        # {'key', 'class', 'type', 'ttl', 'content'}
        for name, node in self.zone.nodes.items():
            rdatasets = node.rdatasets
            for rdataset in rdatasets:
                for rdata in rdataset:
                    record = {}
                    record['key'] = name.to_text(name)
                    record['class'] = dns.rdataclass.to_text(rdataset.rdclass)
                    record['type'] = dns.rdatatype.to_text(rdataset.rdtype)
                    record['ttl'] = str(rdataset.ttl)
                    record['content'] =  rdata.to_text()
                    # filter by record type
                    if record['type'] in self.type_displayed:
                        records.append(record)
        # return the list of records sorted by record type
        return sorted(records, key=itemgetter('type'))  

    @cherrypy.expose
    def index(self, zone=None, **params):
        parse_query_string(cherrypy.request.query_string)
        # zone is defined by the query string parameter
        # if query string is empty, use the default zone
        if zone is None:
            zone = self.zone_default
        try:
            records = self._refresh_zone(zone)
        # exception handling if impossible to get the zone
        # (dns unavailable, misconfiguration, etc)
        except dns.exception.FormError:
            raise cherrypy.HTTPError(500, 'unable to get Zone [' + zone +  ']\
                    from DNS [' + self.zone_list[zone]['ip'] + ']')
        except KeyError:
            raise cherrypy.HTTPError(400, 'Bad Zone [' + zone +  ']')
        return self.temp_index.render(
                records=records, 
                zone_list=self.zone_list,
                default_ttl = self.default_ttl,
                type_written = self.type_written,
                current_zone = zone
                )


    def _manage_record(self, key=None, ttl=None, type=None,
            zone=None, content=None, action=None):
        
        keyring = dns.tsigkeyring.from_text({
            zone : self.zone_list[zone]['key']
        })

        update = dns.update.Update(zone + '.' , keyring=keyring)

        try:
            if action == 'add':
                ttl = int(ttl)
                content = str(content)
                type = str(type)
                update.add(key, ttl, type, content)
            elif action == 'del':
                type = str(type)
                update.delete(key, type)
            else:
                raise NameError('UnhandleDnsUpdateMethod')
        except dns.exception.SyntaxError:
            raise cherrypy.HTTPError(400, 'Wrong form data, bad format')
        except UnknownRdatatype:
            raise cherrypy.HTTPError(500, 'Unknown record type')
        try:
            response = dns.query.tcp(update, self.zone_list[zone]['ip'])
        except PeerBadKey as e:
            raise cherrypy.HTTPError(500, ' Bad auth for zone [' + zone +  ']\
                    on DNS [' + self.zone_list[zone]['ip'] + ']')

    @cherrypy.expose
    def del_record(self, record=None, zone=None):

        # if we select only on entry, it's a string and not a list
        if not isinstance(record, list):
            record = [record]

        for r in record:
            key = (r.split(';'))[0]
            type = (r.split(';'))[1]
            try:
                self._manage_record(key=key, type=type, zone=zone, action='del')
            except 'PeerBadKey':
                raise cherrypy.HTTPError(500, ' Bad auth for [' + zone +  ']\
                    on DNS [' + self.zone_list[zone]['ip'] + ']')


        return "New: " + ' '.join(record)



    @cherrypy.expose
    def add_record(self, key=None, ttl=None, type=None, 
            zone=None, content=None):

        try:
            self._manage_record(key, ttl, type, zone, content, 'add')
        except 'PeerBadKey':
            raise cherrypy.HTTPError(500, ' Bad auth for [' + zone +  ']\
                    on DNS [' + self.zone_list[zone]['ip'] + ']')


        return "New: " + ' '.join([key, ttl, type, content, zone])

cherrypy.quickstart(DnsCherry())
