#    Copyright (C) 2011-2013 University of Southampton
#    Copyright (C) 2011-2013 Daniel Alexander Smith
#    Copyright (C) 2011-2013 Max Van Kleek
#    Copyright (C) 2011-2013 Nigel R. Shadbolt
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License, version 3,
#    as published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
from indx.webserver.handlers.base import BaseHandler
import indx.indx_pg2 as database
from twisted.internet.defer import Deferred

import urlparse
from openid.store import memstore
#from openid.store import filestore
from openid.consumer import consumer
from openid.oidutil import appendArgs
#from openid.cryptutil import randomString
#from openid.fetchers import setDefaultFetcher, Urllib2Fetcher
from openid.extensions import pape, sreg, ax

from indx.openid import IndxOpenID
from hashing_passwords import make_hash, check_hash

OPENID_PROVIDER_NAME = "INDX OpenID Handler"
OPENID_PROVIDER_URL = "http://indx.ecs.soton.ac.uk/"

class AuthHandler(BaseHandler):
    base_path = 'auth'

    # openid store
    store = memstore.MemoryStore()

    # openid URIs
    AX_URIS = [
        'http://schema.openid.net/contact/email',
        'http://schema.openid.net/namePerson/first',
        'http://schema.openid.net/namePerson/last'
    ]

    # authentication
    def auth_login(self, request):
        """ User logged in (POST) """
        ## @TODO : check username/password by authenticating against postgres
        ## 1. check username/password
        ##     if auth -> save username/password in wbsession
        ##                return ok
        ##     else: -> return error

        user = self.get_arg(request, "username")
        pwd = self.get_arg(request, "password")

        if user is None or pwd is None:
            logging.error("auth_login error, user or pwd is None, returning unauthorized")
            return self.return_unauthorized(request)

        def win():
            logging.debug("Login request auth for {0}, origin: {1}".format(user, request.getHeader("Origin")))
            wbSession = self.get_session(request)
            wbSession.setAuthenticated(True)
            wbSession.setUser(user)
            wbSession.setUserType("auth")
            wbSession.setPassword(pwd)
            self.return_ok(request)
        
        def fail():
            logging.debug("Login request fail, origin: {0}".format(self.get_origin(request)))
            wbSession = self.get_session(request)
            wbSession.setAuthenticated(False)
            wbSession.setUser(None)
            wbSession.setUserType(None)
            wbSession.setPassword(None)            
            self.return_unauthorized(request)

        self.database.auth(user,pwd).addCallback(lambda loggedin: win() if loggedin else fail())

    def auth_logout(self, request):
        """ User logged out (GET, POST) """
        logging.debug("Logout request, origin: {0}".format(self.get_origin(request)))
        wbSession = self.get_session(request)
        wbSession.setAuthenticated(False)
        wbSession.setUser(None)
        wbSession.setUserType(None)
        wbSession.setPassword(None)        
        self.return_ok(request)

    def auth_whoami(self, request):
        wbSession = self.get_session(request)
        logging.debug('auth whoami ' + repr(wbSession))
        self.return_ok(request, { "user" : wbSession and wbSession.username or 'nobody', "is_authenticated" : wbSession and wbSession.is_authenticated })
        
    def get_token(self,request):
        ## 1. request contains appid & box being requested (?!)
        ## 2. check session is Authenticated, get username/password

        appid = self.get_arg(request, "app")
        boxid = self.get_arg(request, "box")

        if appid is None or boxid is None:
            logging.error("get_token error, appid or boxid is None, returning bad request.")
            return self.return_bad_request(request)

        wbSession = self.get_session(request)
        if not wbSession.is_authenticated:
            return self.return_unauthorized(request)

        username = wbSession.username
        password = wbSession.password
        origin = self.get_origin(request)

        def got_acct(acct):
            if acct == False:
                return self.return_forbidden(request)

            db_user, db_pass = acct

            def check_app_perms(acct):
                token = self.webserver.tokens.new(username,password,boxid,appid,origin,request.getClientIP())
                return self.return_ok(request, {"token":token.id})

            # create a connection pool
            database.connect_box(boxid,db_user,db_pass).addCallbacks(check_app_perms, lambda conn: self.return_forbidden(request))

        self.database.lookup_best_acct(boxid, username, password).addCallbacks(got_acct, lambda conn: self.return_forbidden(request))

    ### OpenID functions

    def check_openid_pass(self, uri, password):
        """ Check an OpenID user's password. """
        return_d = Deferred()

        logging.debug("check_openid_pass for user {0}, where password is none? {1}".format(uri, password is None))

        def connected_cb(conn):
            """ Get the password hash of a user and check it against the supplied password. """
            d = conn.runQuery("SELECT username_type, password_hash FROM tbl_users WHERE username = %s AND username_type = %s", [uri, "openid"])

            def hash_cb(rows):
                if len(rows) == 0:
                    return_d.callback(False) # return False if user not in DB
                    return

                username_type, password_hash = rows[0]

                if password_hash == "":
                    return_d.callback(True) # user's password is not yet set - return True always.
                    return

                return_d.callback(check_hash(password, password_hash)) # check hash and return result
                return

            d.addCallbacks(hash_cb, return_d.errback)

        # get a connection to the INDX db from the pool
        self.database.connect_indx_db().addCallbacks(connected_cb, return_d.errback)
        return return_d


    def login_openid(self, request):
        """ Verify an OpenID identity. """

        identity = self.get_arg(request, "identity")

        if identity is None:
            logging.error("login_openid error, identity is None, returning bad request.")
            return self.return_bad_request(request, "You must specify an 'identity' in the POST query parameters.")

        password = self.get_arg(request, "password")

        def post_pw():
            logging.debug("login_openid post_pw")

            oid_consumer = consumer.Consumer(self.get_openid_session(request), self.store)
            try:
                oid_req = oid_consumer.begin(identity)
                
                # SReg speaks this protocol: http://openid.net/specs/openid-simple-registration-extension-1_1-01.html
                # and tries to request additional metadata about this OpenID identity
                sreg_req = sreg.SRegRequest(required=['fullname','nickname','email'], optional=[])
                oid_req.addExtension(sreg_req)

                # AX speaks this protocol: http://openid.net/specs/openid-attribute-exchange-1_0.html
                # and tries to get more attributes (by URI), we request some of the more common ones
                ax_req = ax.FetchRequest()
                for uri in self.AX_URIS:
                    ax_req.add(ax.AttrInfo(uri, required = True))
                oid_req.addExtension(ax_req)
            except consumer.DiscoveryFailure as exc:
                #request.setResponseCode(200, message = "OK")
                #request.write("Error: {0}".format(exc))
                #request.finish()
                logging.error("Error in login_openid: {0}".format(exc))
                return self.return_unauthorized(request)
            else:
                if oid_req is None:
                    #request.setResponseCode(200, message = "OK")
                    #request.write("Error, no OpenID services found for: {0}".format(identity))
                    logging.error("Error in login_openid: no OpenID services found for: {0}".format(identity))
                    #request.finish()
                    return self.return_unauthorized(request)
                else:
                    trust_root = self.webserver.server_url
                    return_to = appendArgs(trust_root + "/" + self.base_path + "/openid_process", {})

                    logging.debug("OpenID, had oid_req, trust_root: {0}, return_to: {1}, oid_req: {2}".format(trust_root, return_to, oid_req))

                    redirect_url = oid_req.redirectURL(trust_root, return_to)
                    # FIXME check this is the best way to redirect here
                    request.setHeader("Location", redirect_url)
                    request.setResponseCode(302, "Found")
                    request.finish()
                    return


        def pass_cb(pass_correct):
            logging.error("login_openid pass_cb, password correct? {0}".format(pass_correct))
            if pass_correct:
                return post_pw()
            else:
                return self.return_unauthorized(request)

        self.check_openid_pass(identity, password).addCallbacks(pass_cb, lambda failure: self.return_internal_error(request))
        return


    def openid_process(self, request):
        """ Process a callback from an identity provider. """
        oid_consumer = consumer.Consumer(self.get_openid_session(request), self.store)
        query = urlparse.parse_qsl(urlparse.urlparse(request.uri).query)
        queries = {}
        for key, val in query:
            queries[key] = val
        logging.debug("Queries: {0}".format(queries))
        info = oid_consumer.complete(queries, self.webserver.server_url + "/" + self.base_path + "/openid_process")

        display_identifier = info.getDisplayIdentifier()

        if info.status == consumer.FAILURE and display_identifier:
            #request.setResponseCode(200, "OK")
            logging.error("Verification of {0} failed: {1}".format(display_identifier, info.message))
            #request.finish()
            return self.return_unauthorized(request)
        elif info.status == consumer.SUCCESS:
            sreg_resp = sreg.SRegResponse.fromSuccessResponse(info)
            sreg_data = {}
            if sreg_resp is not None:
                sreg_data = sreg_resp.data
            pape_resp = pape.Response.fromSuccessResponse(info)
            ax_resp = ax.FetchResponse.fromSuccessResponse(info)
            ax_data = {}
            if ax_resp is not None:
                for uri in self.AX_URIS:
                    ax_data[uri] = ax_resp.get(uri)

            logging.debug("openid_process: Success of {0}, sreg_resp: {1} (sreg_data: {2}), pape_resp: {3}, ax_resp: {4}, ax_data: {5}".format(display_identifier, sreg_resp, sreg_data, pape_resp, ax_resp, ax_data))
            if info.endpoint.canonicalID:
                logging.debug("openid_process, additional: ...This is an i-name and its persistent ID is: {0}".format(info.endpoint.canonicalID))

            # Success - User is now INDX authenticated - they can request a token now.
            wbSession = self.get_session(request)
            wbSession.setAuthenticated(True)
            wbSession.setUserType("openid") # TODO FIXME standardise
            wbSession.setUser(display_identifier) # namespace this as a openid or something?
            wbSession.setPassword("") # XXX

            # Initialise the OpenID user now:

            ix_openid = IndxOpenID(self.database, display_identifier)

            def err_cb(err):
                logging.error("Error in IndxOpenID: {0}".format(err))
                return self.return_unauthorized(request)

            def cb(user_info):
                password_hash = user_info['password_hash']
                if password_hash == "":
                    # user should be prompted for a password by the UI now, because they never have set one (new OpenID user)
                    # TODO do this...
                    return self.return_ok(request)
                else:
                    return self.return_ok(request)
    
            ix_openid.init_user().addCallbacks(cb, err_cb)
            return
            #return self.return_ok(request)
        elif info.status == consumer.CANCEL:
            #request.setResponseCode(200, "OK")
            logging.error("Error in openid_process: Verification cancelled.")
            #request.finish()
            return self.return_unauthorized(request)
        elif info.status == consumer.SETUP_NEEDED:
            #request.setResponseCode(200, "OK")
            logging.error("Error in openid_process: Setup needed at URL: {0}".format(info.setup_url))
            #request.finish()
            return self.return_unauthorized(request)
        else:
            #request.setResponseCode(200, "OK")
            logging.error("Error in openid_process: Verification Failed.")
            #request.finish()
            return self.return_unauthorized(request)


    def get_openid_session(self, request):
        return self.get_session(request).get_openid_session()


AuthHandler.subhandlers = [
    {
        'prefix':'whoami',
        'methods': ['GET'],
        'require_auth': False,
        'require_token': False,
        'handler': AuthHandler.auth_whoami,
        'content-type':'text/plain', # optional
        'accept':['application/json']      
    },    
    {
        'prefix':'login',
        'methods': ['POST'],
        'require_auth': False,
        'require_token': False,
        'handler': AuthHandler.auth_login,
        'content-type':'text/plain', # optional
        'accept':['application/json']                
        },
    {
        # for a google plus account
        # http://localhost:8211/auth/login_openid?identity=https://plus.google.com/114976418317566143717
        # for an INDX ID account
        # http://localhost:8211/auth/login_openid?identity=http://id.indx.ecs.soton.ac.uk/identity/ds
        'prefix':'login_openid', # login with openid
        'methods': ['POST'],
        'require_auth': False,
        'require_token': False,
        'handler': AuthHandler.login_openid,
        'content-type':'text/plain', # optional
        'accept':['application/json']                
        },
    {
        'prefix':'openid_process', # callback from the remote system with a success/fail, to the local browser
        'methods': ['GET'],
        'require_auth': False,
        'require_token': False,
        'handler': AuthHandler.openid_process,
        'content-type':'text/plain', # optional
        'accept':['application/json']                
        },
    {
        'prefix':'logout',
        'methods': ['POST', 'GET'],
        'require_auth': True,
        'require_token': False,
        'handler': AuthHandler.auth_logout,
        'content-type':'text/plain', # optional
        'accept':['application/json']        
    },
    {
        'prefix':'get_token',
        'methods': ['POST'],
        'require_auth': True,
        'require_token': False,
        'handler': AuthHandler.get_token,
        'content-type':'application/json', 
        'accept':['application/json']                
    },
    {
        'prefix':'logout',
        'methods': ['POST', 'GET'],
        'require_auth': False,
        'require_token': False,
        'handler': AuthHandler.return_ok, # already logged out
        'content-type':'text/plain', # optional
        'accept':['application/json']                
        },
     {
        'prefix':'*',
        'methods': ['OPTIONS'],
        'require_auth': False,
        'require_token': False,
        'handler': AuthHandler.return_ok, # already logged out
        'content-type':'text/plain', # optional
        'accept':['application/json']                
     }    
]


