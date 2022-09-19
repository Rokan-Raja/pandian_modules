# -*- coding: utf-8 -*-
###################################################################################
#
#    Shorepointsystem Private Limited
#    Author: Roja (29-08-2019)
#
#
###################################################################################

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
  _inherit = 'account.move'
  
    
  def reverse_moves(self, date=None, journal_id=None):
    date = date or fields.Date.today()
    reversed_moves = self.env['account.move']
    for ac_move in self:
      reversed_move = ac_move._reverse_move(date=date,
                                            journal_id=journal_id)
      reversed_moves |= reversed_move
      #unreconcile all lines reversed
      aml = ac_move.line_ids.filtered(lambda x: x.account_id.reconcile or x.account_id.internal_type == 'liquidity')
      aml.remove_move_reconcile()
      bounced = aml.cheque_bouncing()
      #reconcile together the reconciliable (or the liquidity aml) and their newly created counterpart
      for account in list(set([x.account_id for x in aml])):
        to_rec = aml.filtered(lambda y: y.account_id == account)
        to_rec |= reversed_move.line_ids.filtered(lambda y: y.account_id == account)
        #reconciliation will be full, so speed up the computation by using skip_full_reconcile_check in the context
        to_rec.with_context(skip_full_reconcile_check=True).reconcile()
        to_rec.force_full_reconcile()
    if reversed_moves:
      _logger.info("reversed_moves:%s" %reversed_moves)
      reversed_moves._post_validate()
      reversed_moves.post()
      return [x.id for x in reversed_moves]
      return []

class AccountMoveLine(models.Model):
  _inherit = 'account.move.line'
  
  def cheque_bouncing(self):
    """ Move cheques to Bounced State """
    bounced = []
    if not self:
      return 
    for account_move_line in self:
      cheque = account_move_line.payment_id.cheque_id
      if cheque and cheque.id:
        cheque.action_cheque_bounced()
        bounced.append({'move': account_move_line})
    return bounced    
        
    
  def remove_move_reconcile(self):
    """ Undo a reconciliation """
    if not self:
      return True
    rec_move_ids = self.env['account.partial.reconcile']
    for account_move_line in self:
      payment = account_move_line.payment_id
      payment.update_available_credit(-payment.amount,payment.partner_id.id)
      for invoice in account_move_line.payment_id.invoice_ids:
        if invoice.id == self.env.context.get('invoice_id') and account_move_line in invoice.payment_move_line_ids:
          account_move_line.payment_id.write({'invoice_ids': [(3, invoice.id, None)]})
      rec_move_ids += account_move_line.matched_debit_ids
      rec_move_ids += account_move_line.matched_credit_ids
    return rec_move_ids.unlink()
