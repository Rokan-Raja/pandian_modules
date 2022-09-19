# -*- coding: utf-8 -*-
from odoo import http

# class Cheques(http.Controller):
#     @http.route('/cheques/cheques/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/cheques/cheques/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('cheques.listing', {
#             'root': '/cheques/cheques',
#             'objects': http.request.env['cheques.cheques'].search([]),
#         })

#     @http.route('/cheques/cheques/objects/<model("cheques.cheques"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('cheques.object', {
#             'object': obj
#         })