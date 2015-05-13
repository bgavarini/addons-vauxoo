# -*- encoding: utf-8 -*-
from openerp.osv import osv, fields
from openerp.tools.safe_eval import safe_eval
from openerp import SUPERUSER_ID

import re


def clean_name(name):
    exp = r'\[.*?\]'
    text = name.strip()
    found = re.findall(exp, text)
    if found:
        for f in found:
            text = text.replace(f, '').strip()
    words = text.split(' ')
    if len(words) > 2:
        text = ' '.join([words[0], words[2]])
    return text


class fiscal_book_wizard(osv.Model):

    _name = "hr.timesheet.reports.base"
    _inherit = ['mail.thread']

    def _prepare_data(self, record):
        return {'author': clean_name(record.user_id.name),
                'description': record.name,
                'duration': record.unit_amount,
                'invoiceables_hours': record.invoiceables_hours,
                'date': record.date,
                'analytic': record.account_id.name,
                'id': record.id,
                }

    def _get_print_data(self, cr, uid, ids, name, args, context=None):
        res = {}
        for wzd in self.browse(cr, uid, ids, context=context):
            res[wzd.id] = self._get_result_ids(cr, uid, ids, context=context)
        return res

    def _get_total_time(self, grouped, field):
        total_list = [g[field] for g in grouped]
        return sum(total_list)

    def _get_report_inv(self, cr, uid, ids, context=None):
        invoice_obj = self.pool.get('account.invoice')
        wzr_brw = self.browse(cr, uid, ids, context=context)[0]
        domain_inv = wzr_brw.filter_invoice_id and \
            wzr_brw.filter_invoice_id.domain or []
        if not domain_inv:
            return ([], [], [])
        dom_inv = [len(d) > 1 and tuple(d) or d for d in safe_eval(domain_inv)]
        # Preparing grouped invoices due to it is 2 levels it need a
        # little extra Work.
        elements = invoice_obj.read_group(cr, uid, dom_inv,
                                          ['period_id',
                                           'amount_total',
                                           'residual',
                                           'partner_id'
                                           ],
                                          ['period_id',
                                           'amount_total',
                                           'residual',
                                           ],
                                          context=context)
        grouped_by_currency = invoice_obj.read_group(cr, uid, dom_inv,
                                                     ['currency_id',
                                                      'amount_total',
                                                      'residual',
                                                      'partner_id'
                                                      ],
                                                     ['currency_id',
                                                      'amount_total',
                                                      'residual',
                                                      ],
                                                     context=context)
        #  TODO: This must be a better way to achieve this list directly from
        #  search group on v8.0 for now the simplest way make a list with
        #  everything an group in the report itself
        invoice_ids = invoice_obj.search(cr, uid, dom_inv, context=context)
        invoices_brw = invoice_obj.browse(cr, uid, invoice_ids,
                                          context=context)

        return (elements, grouped_by_currency, invoices_brw)

    def _get_report_hus(self, cr, uid, ids, context=None):
        hu_obj = self.pool.get('user.story')
        wzr_brw = self.browse(cr, uid, ids, context=context)[0]
        domain_hu = wzr_brw.filter_hu_id and wzr_brw.filter_hu_id.domain or []
        if not domain_hu:
            return []
        dom_hu = [len(d) > 1 and tuple(d) or d for d in safe_eval(domain_hu)]
        # Setting the HU elements
        hu_ids = hu_obj.search(cr, uid, dom_hu,
                               order='state asc', context=context)
        hu_brw = hu_obj.browse(cr, uid, hu_ids, context=context)
        return hu_brw

    def _get_report_issue(self, cr, uid, ids, context=None):
        issue_obj = self.pool.get('project.issue')
        wzr_brw = self.browse(cr, uid, ids, context=context)[0]
        domain_issues = wzr_brw.filter_issue_id and \
            wzr_brw.filter_issue_id.domain or []
        if not domain_issues:
            return []
        dom_issues = [len(d) > 1 and tuple(d) or d
                      for d in safe_eval(domain_issues)]
        # Setting issues elements.
        issues_grouped = issue_obj.read_group(cr, uid, dom_issues,
                                              ['analytic_account_id'],
                                              ['analytic_account_id'],
                                              context=context)

        issues_all = []
        for issue in issues_grouped:
            analytic_id = issue.get('analytic_account_id')
            new_issue_dom = dom_issues + [('analytic_account_id', '=', analytic_id and analytic_id[0] or analytic_id)]  # noqa
            issue['children_by_stage'] = issue_obj.read_group(cr, uid, new_issue_dom,  # noqa
                                                              ['stage_id'],
                                                              ['stage_id'],
                                                              orderby='stage_id asc',  # noqa
                                                              context=context)
            issues_all.append(issue)
        return issues_all

    def _get_report_ts(self, cr, uid, ids, context=None):
        timesheet_obj = self.pool.get('hr.analytic.timesheet')
        wzr_brw = self.browse(cr, uid, ids, context=context)[0]
        domain = wzr_brw.filter_id.domain
        dom = [len(d) > 1 and tuple(d) or d for d in safe_eval(domain)]
        timesheet_ids = timesheet_obj.search(cr, uid, dom,
                                             order='account_id asc, user_id asc, date asc',  # noqa
                                             context=context)
        # Group elements
        res = []
        timesheet_brws = timesheet_obj.browse(cr, uid, timesheet_ids,
                                              context=context)
        res = [self._prepare_data(tb) for tb in timesheet_brws]
        grouped = timesheet_obj.read_group(cr, uid, dom,
                                           ['account_id',
                                            'unit_amount',
                                            'invoiceables_hours'],
                                           ['account_id'],
                                           context=context)
        grouped_month = timesheet_obj.read_group(cr, uid, dom,
                                                 ['date',
                                                  'account_id',
                                                  'unit_amount',
                                                  'invoiceables_hours'],
                                                 ['date'],
                                                 context=context)
        # Separate per project (analytic)
        projects = set([l['analytic'] for l in res])
        return (grouped, grouped_month, projects, res)

    def _get_result_ids(self, cr, uid, ids, context=None):
        uid = SUPERUSER_ID
        gi, gbc, ibrw = self._get_report_inv(cr, uid, ids, context=context)
        grouped, grouped_month, projects, res = self._get_report_ts(cr, uid,
                                                                    ids,
                                                                    context=context)  # noqa
        info = {
            'data': {},
            'resume': grouped,
            'resume_month': grouped_month,
            'invoices': ibrw,
            'issues': self._get_report_issue(cr, uid,
                                             ids, context=context),
            'user_stories': self._get_report_hus(cr, uid,
                                                 ids, context=context),
            'total_ts_bill_by_month': self._get_total_time(grouped,
                                                           'invoiceables_hours'),  # noqa
            'total_ts_by_month': self._get_total_time(grouped,
                                                      'unit_amount'),
            'periods': gi,
            'total_invoices': gbc,
        }
        for proj in projects:
            info['data'][proj] = [r for r in res if r['analytic'] == proj]
        return info

    _columns = {
        'name': fields.char('Report Title'),
        'comment_invoices': fields.text('Comment about Invoices',
                                        help="It will appear just above "
                                        "list of invoices."),
        'comment_timesheet': fields.text('Comment about Timesheets',
                                         help='It will appear just above '
                                         'the resumed timesheets.'),
        'comment_issues': fields.text('Comment about Timesheets',
                                      help='It will appear just above '
                                      'the resumed issues.'),
        'comment_hu': fields.text('Comment about Timesheets',
                                  help='It will appear just above '
                                  'the resumed hu status.'),
        'user_id': fields.many2one(
            'res.users', 'Responsible',
            help='Owner of the report, generally the person that create it.'),
        'partner_id': fields.many2one(
            'res.partner', 'Contact',
            help='Contact which you will send this report.'),
        'filter_hu_id': fields.many2one(
            'ir.filters', 'User Stories',
            domain=[('model_id', 'ilike', 'user.story')],
            help='Set the filter for issues TIP: go to issues and look for '
            'the filter that adjust to your needs of issues to be shown.'),
        'filter_issue_id': fields.many2one(
            'ir.filters', 'Issues',
            domain=[('model_id', 'ilike', 'project.issue')],
            help='Set the filter for issues TIP: go to issues and look for '
            'the filter that adjust to your needs of issues to be shown.'),
        'filter_invoice_id': fields.many2one(
            'ir.filters', 'Invoices',
            domain=[('model_id', 'ilike', 'account.invoice')],
            help='Filter of Invoices to be shown TIP: '
            'Go to Accounting/Customer '
            'Invoices in order to create the filter you want to show on this'
            'report.',),
        'filter_id': fields.many2one(
            'ir.filters', 'Filter',
            domain=[('model_id', 'ilike', 'hr.analytic.timesheet')],
            help="Filter should be by date, group_by is ignored, the model "
            "which the filter should belong to is timesheet."),
        'records': fields.function(_get_print_data,
                                   string='Records', type="text"),
        'state': fields.selection([('draft', 'Draft'),
                                   ('sent', 'Sent')],
                                  'Status',
                                  help='Message sent already to customer (it will block edition)'),
        'company_id': fields.many2one(
            'res.company', 'Company',
            help='Company which this report belongs to'),
    }

    _defaults = {
        'state': lambda * a: 'draft',
        'user_id': lambda obj, cr, uid, context: uid,
        'company_id': lambda s, cr, uid, c: s.pool.get('res.company')._company_default_get(cr, uid, 'sale.shop', context=c),
    }

    def do_report(self, cr, uid, ids, context=None):
        return {'type': 'ir.actions.report.xml',
                'name': 'hr.timesheet.reports.explain',
                'report_name': 'Resumed Project Status',
                'report_type': "webkit",
                'string': "Hr timesheet reports base",
                'file': "hr_timesheet_reports/model/hr_timesheet_reports_base.mako",  # noqa
                'nodestroy': True,
                }

    def send_by_email(self, cr, uid, ids, context=None, cdsm=None):
        ir_model_data = self.pool.get('ir.model.data')
        try:
            template_id = ir_model_data.get_object_reference(cr, uid, 'hr_timesheet_reports', 'email_reports_base')[1]
        except ValueError:
            template_id = False
        try:
            compose_form_id = ir_model_data.get_object_reference(cr, uid, 'mail', 'email_compose_message_wizard_form')[1]
        except ValueError:
            compose_form_id = False
        ctx = dict(context)
        ctx.update({
            'default_model': 'hr.timesheet.reports.base',
            'default_res_id': ids[0],
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True
        })
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form_id, 'form')],
            'view_id': compose_form_id,
            'target': 'new',
            'context': ctx,
        }

    def mark_timesheet(self, cr, uid, ids, context=None):
        return True

    def clean_timesheet(self, cr, uid, ids, context=None):
        '''
        To be sure all timesheet lines are at least setted as billable
        100% in order to show correct first approach of numbers.
        '''
        timesheet_obj = self.pool.get('hr.analytic.timesheet')
        report = self.browse(cr, uid, ids, context=context)[0]
        domain = report.filter_id.domain
        dom = [len(d) > 1 and tuple(d) or d for d in safe_eval(domain)]
        timesheet_ids = timesheet_obj.search(cr, uid,
                                              dom + [('to_invoice', '=', False)],  # noqa
                                              context=context)  # noqa
        # By default 100% wired to the one by default in db.
        # If you want another one overwrite this method or change the
        # rate on such record.
        timesheet_obj.write(cr, uid,
                            timesheet_ids,
                            {'to_invoice': 1},
                            context=context)
        return True
