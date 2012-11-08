#    This file is part of WebBox.
#
#    Copyright 2011-2012 Daniel Alexander Smith
#    Copyright 2011-2012 University of Southampton
#
#    WebBox is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    WebBox is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with WebBox.  If not, see <http://www.gnu.org/licenses/>.

import logging, traceback
from twisted.web.resource import Resource
from session import WebBoxSession, ISession

class AuthHandler(BaseHandler):

    base_path = 'auth'
    subhandlers = {
        'login': {
            'methods': ['POST'],
            'require_auth': False,
            'require_token': False,
            'handler': AuthHandler.auth_login,
            'content-type':'text/plain' # optional
        },
        'logout': {
            'methods': ['POST', 'GET'],
            'require_auth': True,
            'require_token': False,
            'handler': AuthHandler.auth_logout,
            'content-type':'text/plain' # optional
        }        
    }
    
    # authentication
    def auth_login(self, request):
        """ User logged in (POST) """
        logging.debug("Login request, origin: {0}".format(request.getHeader("Origin")))
        session = request.getSession()
        wbSession = session.getComponent(ISession)
        wbSession.setAuthenticated(True)
        wbSession.setUser(0, "anonymous")
        request.setStatusCode(200, reason="OK")
        request.finish()

    def auth_logout(self, request):
        """ User logged out (GET, POST) """
        logging.debug("Logout request, origin: {0}".format(request.getHeader("Origin")))
        session = request.getSession()
        wbSession = session.getComponent(ISession)
        wbSession.setAuthenticated(False)
        wbSession.setUser(None, None)
        request.setStatusCode(200, reason="OK")
        request.finish()



