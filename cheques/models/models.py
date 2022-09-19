# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from datetime import datetime
from odoo.osv import expression
from odoo.tools import float_is_zero, pycompat
from odoo.tools import float_compare, float_round, float_repr
from odoo.tools.misc import formatLang
from odoo.exceptions import UserError, ValidationError

import time
import math

_logger = logging.getLogger(__name__)

#----------------(Roja 7-9-18)Cheque register------------
class cheques(models.Model):
    _name = 'payment.cheques'
    _rec_name='cheque_no'
    _order = "issue_date desc, date desc"
    
    
    cheque_no = fields.Char(string="Cheque No", required=True)
    issue_date = fields.Date(string="Date",required=True,default=fields.Date.context_today)
    partner_type = fields.Selection([('customer_rank', 'Customer'), ('supplier_rank', 'Vendor')],default='customer')
    partner_id = fields.Many2one('res.partner', string='Partner',required=True)
    cheque_bank = fields.Char(string="Cheque Bank",required=True)
    date = fields.Date(string="Cheque Date",required=True)
    cheque_amount=fields.Float(string='Cheque Amount', required=True)
    communication = fields.Char(string="Payment Reference")
    cheque_journal_id = fields.Many2one(string="Journal",comodel_name="account.journal",domain=[('type', '=', 'bank')],required=True)
    employee_id= fields.Many2one('hr.employee', string='Employee')
    date_change=fields.Boolean()
    check=fields.Boolean()
    reason = fields.Char(string="Reason")
    cheque_presenting_date = fields.Date(string="Cheque Presenting Date")
    cheque_clearing_date = fields.Date(string="Cheque Clearing Date")
    move_id = fields.Many2one('account.move' , string='Move Line')
    statement_line= fields.Many2one('account.bank.statement.line' , string='Statement Line')
    date_change_ids = fields.One2many('payment.cheques.date.change', 'cheque_id', string='Cheque Date change')
    state = fields.Selection([('new', 'New'),('received', 'Received'), ('send', 'Send to bank'), ('cleared', 'Cleared'), ('bounced', 'Bounced')], readonly=True, default='new', copy=False, string="Status")
    pos_session_id = fields.Many2one('pos.session',string="POS Session")
    payment_id = fields.Many2one('account.payment', string = 'Payment')


    _sql_constraints = [
        ('chq_no_uniq', 'unique (cheque_no)', 'The cheque number must be unique.!')
    ]

    @api.model
    def get_cheque_date(self):
        _logger.info("selfff %s" %self)
    @api.onchange('partner_type')
    def _onchange_partner_type(self):
        # Set partner_id domain
        if self.partner_type:
            return {'domain': {'partner_id': [(self.partner_type, '>', 0)]}}

    @api.model
    def create(self, values):
        values['state']='received'
        line = super(cheques, self).create(values)
        return line

      
    def unlink(self):
        for cheque in self:
            if cheque.state in ('send', 'cleared'):
                raise UserError(_('You can not delete a Cheque which is Send to bank Or Cleared state!'))
        return super(cheques, self).unlink()

    #Change cheques state to Bounced
    def action_cheque_bounced(self):
      self.write({'state': 'bounced'})
      return

#----------------(Roja 7-9-18)Cheque date changes------------
class chequesdatechange(models.Model):
    _name= 'payment.cheques.date.change'
    date_from=fields.Date(string='From Date',required=True,default=lambda self: self._context.get('date', fields.Date.context_today(self)))
    date_to= fields.Date(string= 'To Date',required=True)
    reason = fields.Char(string='Reason',required=True)
    cheque_id = fields.Many2one('payment.cheques', string='Cheque')
    state_close= fields.Boolean()
    @api.model
    def create(self, vals):
        line = super(chequesdatechange, self).create(vals)
        _logger.info("cheque ---%s" %line.cheque_id)
        cheque_obj = self.env['payment.cheques'].browse(line.cheque_id.id)
        cheque_obj.write({'date' : line.date_to})
        return line

class SendToBank(models.TransientModel):
    _name = "payment.cheques.send.bank"
    employee_id= fields.Many2one('hr.employee', string='Responsible Employee')
    
    def sending_cheques_to_bank(self,cheques):
        today_date = (datetime.today()).strftime("%Y-%m-%d")
        for cheque in cheques:
            if cheque.date <= today_date:
                cheque.write({'state' : 'send','employee_id':self.employee_id.id,'cheque_presenting_date':today_date})
                cheque.payment_id.post()
            else:
                raise UserError(_('Cheque:%s Cannot Send to Bank Before Cheque Date.' %cheque.cheque_no))
      
    def send_to_bank(self):
        cheque_obj = self.env['payment.cheques']
        cheques = cheque_obj.browse(self._context.get('active_ids'))
        return self.sending_cheques_to_bank(cheques)
        
    @api.model
    def send_to_bank_from_ui(self,cheques):
        cheque_obj = self.env['payment.cheques']
        cheques = cheque_obj.browse(tuple(cheques))
        return self.sending_cheques_to_bank(cheques)

#-------------(Roja 10-9-18)Check clearance--------------
class InheritChequeAccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    def process_reconciliation(self, counterpart_aml_dicts=None, payment_aml_rec=None, new_aml_dicts=None):
        _logger.info("counterpart_aml_dicts:%s,payment_aml_rec:%s,new_aml_dicts:%s"%(counterpart_aml_dicts,payment_aml_rec,new_aml_dicts))
        counterpart_aml_dicts = counterpart_aml_dicts or []
        payment_aml_rec = payment_aml_rec or self.env['account.move.line']
        new_aml_dicts = new_aml_dicts or []

        aml_obj = self.env['account.move.line']

        company_currency = self.journal_id.company_id.currency_id
        statement_currency = self.journal_id.currency_id or company_currency
        st_line_currency = self.currency_id or statement_currency

        counterpart_moves = self.env['account.move']

        # Check and prepare received data
        if any(rec.statement_id for rec in payment_aml_rec):
            raise UserError(_('A selected move line was already reconciled.'))
        for aml_dict in counterpart_aml_dicts:
            if aml_dict['move_line'].reconciled:
                raise UserError(_('A selected move line was already reconciled.'))
            if isinstance(aml_dict['move_line'], pycompat.integer_types):
                aml_dict['move_line'] = aml_obj.browse(aml_dict['move_line'])
        for aml_dict in (counterpart_aml_dicts + new_aml_dicts):
            if aml_dict.get('tax_ids') and isinstance(aml_dict['tax_ids'][0], pycompat.integer_types):
                # Transform the value in the format required for One2many and Many2many fields
                aml_dict['tax_ids'] = [(4, id, None) for id in aml_dict['tax_ids']]
        if any(line.journal_entry_ids for line in self):
            raise UserError(_('A selected statement line was already reconciled with an account move.'))

        # Fully reconciled moves are just linked to the bank statement
        total = self.amount
        _logger.info("statement payment_aml_rec %s " % (payment_aml_rec))
        for aml_rec in payment_aml_rec:
            total -= aml_rec.debit - aml_rec.credit
            aml_rec.with_context(check_move_validity=False).write({'statement_line_id': self.id})
            counterpart_moves = (counterpart_moves | aml_rec.move_id)
            if aml_rec.payment_id.payment_type_mode == 'cheque':
              aml_rec.payment_id.cheque_id.write({'state' : 'cleared','statement_line':self.id,'move_id':aml_rec.move_id.id,'cheque_clearing_date':(datetime.today()).strftime("%Y-%m-%d")})
            
        _logger.info("statement counterpart_aml_dicts %s " % (counterpart_aml_dicts))
        _logger.info("statement new_aml_dicts %s " % (new_aml_dicts))
        
        # Create move line(s). Either matching an existing journal entry (eg. invoice), in which
        # case we reconcile the existing and the new move lines together, or being a write-off.
        if counterpart_aml_dicts or new_aml_dicts:
            _logger.info("statement reconcile %s:%s " % (self.partner_id.name,self.amount))
            st_line_currency = self.currency_id or statement_currency
            st_line_currency_rate = self.currency_id and (self.amount_currency / self.amount) or False

            # Create the move
            self.sequence = self.statement_id.line_ids.ids.index(self.id) + 1
            move_vals = self._prepare_reconciliation_move(self.statement_id.name)
            move = self.env['account.move'].create(move_vals)
            counterpart_moves = (counterpart_moves | move)

            # Create The payment
            payment = self.env['account.payment']
            if abs(total)>0.00001:
                partner_id = self.partner_id and self.partner_id.id or False
                partner_type = False
                if partner_id:
                    if total < 0:
                        partner_type = 'supplier'
                    else:
                        partner_type = 'customer'

                payment_methods = (total>0) and self.journal_id.inbound_payment_method_ids or self.journal_id.outbound_payment_method_ids
                currency = self.journal_id.currency_id or self.company_id.currency_id
                payment = self.env['account.payment'].create({
                    'payment_method_id': payment_methods and payment_methods[0].id or False,
                    'payment_type': total >0 and 'inbound' or 'outbound',
                    'partner_id': self.partner_id and self.partner_id.id or False,
                    'partner_type': partner_type,
                    'journal_id': self.statement_id.journal_id.id,
                    'payment_date': self.date,
                    'state': 'reconciled',
                    'currency_id': currency.id,
                    'amount': abs(total),
                    'communication': self._get_communication(payment_methods[0] if payment_methods else False),
                    'name': self.statement_id.name,

                })

            # Complete dicts to create both counterpart move lines and write-offs
            to_create = (counterpart_aml_dicts + new_aml_dicts)
            ctx = dict(self._context, date=self.date)
            for aml_dict in to_create:
                aml_dict['move_id'] = move.id
                aml_dict['partner_id'] = self.partner_id.id
                aml_dict['statement_line_id'] = self.id
                if st_line_currency.id != company_currency.id:
                    aml_dict['amount_currency'] = aml_dict['debit'] - aml_dict['credit']
                    aml_dict['currency_id'] = st_line_currency.id
                    if self.currency_id and statement_currency.id == company_currency.id and st_line_currency_rate:
                        # Statement is in company currency but the transaction is in foreign currency
                        aml_dict['debit'] = company_currency.round(aml_dict['debit'] / st_line_currency_rate)
                        aml_dict['credit'] = company_currency.round(aml_dict['credit'] / st_line_currency_rate)
                    elif self.currency_id and st_line_currency_rate:
                        # Statement is in foreign currency and the transaction is in another one
                        aml_dict['debit'] = statement_currency.with_context(ctx).compute(aml_dict['debit'] / st_line_currency_rate, company_currency)
                        aml_dict['credit'] = statement_currency.with_context(ctx).compute(aml_dict['credit'] / st_line_currency_rate, company_currency)
                    else:
                        # Statement is in foreign currency and no extra currency is given for the transaction
                        aml_dict['debit'] = st_line_currency.with_context(ctx).compute(aml_dict['debit'], company_currency)
                        aml_dict['credit'] = st_line_currency.with_context(ctx).compute(aml_dict['credit'], company_currency)
                elif statement_currency.id != company_currency.id:
                    # Statement is in foreign currency but the transaction is in company currency
                    prorata_factor = (aml_dict['debit'] - aml_dict['credit']) / self.amount_currency
                    aml_dict['amount_currency'] = prorata_factor * self.amount
                    aml_dict['currency_id'] = statement_currency.id

            # Create write-offs
            # When we register a payment on an invoice, the write-off line contains the amount
            # currency if all related invoices have the same currency. We apply the same logic in
            # the manual reconciliation.
            counterpart_aml = self.env['account.move.line']
            for aml_dict in counterpart_aml_dicts:
                counterpart_aml |= aml_dict.get('move_line', self.env['account.move.line'])
            new_aml_currency = False
            if counterpart_aml\
                    and len(counterpart_aml.mapped('currency_id')) == 1\
                    and counterpart_aml[0].currency_id\
                    and counterpart_aml[0].currency_id != company_currency:
                new_aml_currency = counterpart_aml[0].currency_id
            for aml_dict in new_aml_dicts:
                aml_dict['payment_id'] = payment and payment.id or False
                if new_aml_currency and not aml_dict.get('currency_id'):
                    aml_dict['currency_id'] = new_aml_currency.id
                    aml_dict['amount_currency'] = company_currency.with_context(ctx).compute(aml_dict['debit'] - aml_dict['credit'], new_aml_currency)
                aml_obj.with_context(check_move_validity=False, apply_taxes=True).create(aml_dict)

            # Create counterpart move lines and reconcile them
            for aml_dict in counterpart_aml_dicts:
                if aml_dict['move_line'].partner_id.id:
                    aml_dict['partner_id'] = aml_dict['move_line'].partner_id.id
                aml_dict['account_id'] = aml_dict['move_line'].account_id.id
                aml_dict['payment_id'] = payment and payment.id or False

                counterpart_move_line = aml_dict.pop('move_line')
                if counterpart_move_line.currency_id and counterpart_move_line.currency_id != company_currency and not aml_dict.get('currency_id'):
                    aml_dict['currency_id'] = counterpart_move_line.currency_id.id
                    aml_dict['amount_currency'] = company_currency.with_context(ctx).compute(aml_dict['debit'] - aml_dict['credit'], counterpart_move_line.currency_id)
                new_aml = aml_obj.with_context(check_move_validity=False).create(aml_dict)

                (new_aml | counterpart_move_line).reconcile()

            # Balance the move
            st_line_amount = -sum([x.balance for x in move.line_ids])
            aml_dict = self._prepare_reconciliation_move_line(move, st_line_amount)
            aml_dict['payment_id'] = payment and payment.id or False
            aml_obj.with_context(check_move_validity=False).create(aml_dict)

            move.post()
            #record the move name on the statement line to be able to retrieve it in case of unreconciliation
            self.write({'move_name': move.name})
            payment and payment.write({'payment_reference': move.name})
           
            _logger.info("self.name.lower():%s" %self.name.lower())
            
            #Card Transaction identification
            card_transaction_key_words = ['bulk posting','card']
            arr = ['neft','rtgs']
            if any(c in self.name.lower() for c in card_transaction_key_words):
                _logger.info("Card")
                payment.write({'payment_type_mode': 'card'})
            
            #NEFT Transaction identification
            elif 'neft' in self.name.lower():
                _logger.info("NEFT")
                payment.write({'payment_type_mode': 'neft'})


            #rtgs Transaction identification
            elif 'rtgs' in self.name.lower():
                _logger.info("RTGS")
                payment.write({'payment_type_mode': 'rtgs'})
                
            #E-payment identification
            
            elif 'inb' in self.name.lower() and not any(c in self.name.lower() for c in arr):
                  _logger.info("E-payment")
                  payment.write({'payment_type_mode': 'efund'})
            
            for invoice in counterpart_aml_dicts:
              if invoice['credit']:
                 amount=invoice['credit'] 
              if invoice['debit']:
                 amount=invoice['debit']
              self.env['account.payment'].update_available_credit(amount,invoice['partner_id'])
                 
            #Clear the check
            chq_code = ['cheque','chq'] 
            if any(c in self.name.lower() for c in chq_code):
                payment.write({'payment_type_mode': 'cheque'})
                for invoice in counterpart_aml_dicts:
                    cheque = self.env['payment.cheques'].search([
			    ('partner_id', '=', invoice['partner_id']),
			    ('cheque_amount', '=', self.amount),		   
			    ('state', '=', 'send')],limit=1)
                    if cheque:
                       cheque.write({'state' : 'cleared','statement_line':invoice['statement_line_id'],'move_id':invoice['move_id'],'cheque_clearing_date':(datetime.today()).strftime("%Y-%m-%d")})
                       payment.write({'cheque_id':cheque.id})
        elif self.move_name:
            raise UserError(_('Operation not allowed. Since your statement line already received a number, you cannot reconcile it entirely with existing journal entries otherwise it would make a gap in the numbering. You should book an entry and make a regular revert of it in case you want to cancel it.'))
        counterpart_moves.assert_balanced()
        _logger.info("process reconcilation..:%s" %aml_obj)
        return counterpart_moves
