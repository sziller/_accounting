from decimal import Decimal as D, ROUND_HALF_UP, localcontext
from dataclasses import replace
from datetime import date
import unittest
from app.domain.ar_amount_allocation import allocate_invoice_amounts, _component_quantum
from app.domain.ar_recognition import ArInvoiceRecognitionFacts, ArAllocationRecognitionFacts, resolve_ar_recognition_events


class CumulativeAllocationTests(unittest.TestCase):
    def shares(self, totals, amounts, gross='100'):
        return allocate_invoice_amounts(gross_total=D(gross), net_total=totals[0],
            vat_total=totals[1], common_total=totals[2], recognized_gross_amounts=tuple(map(D, amounts)))

    def test_quantum_ignores_trailing_zeros_without_context_rounding(self):
        with localcontext() as context:
            context.prec = 2
            for value, quantum in [('19.000','.01'),('0.006','.001'),('1.234500','.0001'),
                                   ('123456789.12345600','.000001'),('0.000000','.01')]:
                self.assertEqual(_component_quantum(D(value)),D(quantum))

    def test_tiny_final_receipt_and_independent_component_precision(self):
        totals=(D('.006'),D('1.2345'),D('19.000'))
        shares=self.shares(totals,('99.99','.01'))
        self.assertEqual([s.net_amount_original for s in shares],[D('.006'),D('0')])
        self.assertEqual([s.vat_amount_original for s in shares],[D('1.2344'),D('.0001')])
        self.assertEqual([s.amount_common for s in shares],[D('19.00'),D('0')])
        # Former independently rounded .01 + .01 would overconsume a .01 total.
        shares=self.shares((D('.01'),)*3,('49','49','2'))
        self.assertEqual([s.amount_common for s in shares],[D('0'),D('.01'),D('0')])
        # More direct old negative-final example: .51 + .48 + .01 of gross 1.
        shares=self.shares((D('.03'),)*3,('.51','.48','.01'),gross='1')
        self.assertEqual([s.amount_common for s in shares],[D('.02'),D('.01'),D('0')])

    def test_prefix_targets_nonnegative_reconciliation_and_append_stability(self):
        fields=('net_amount_original','vat_amount_original','amount_common')
        for totals in ((D('19.000'),D('.006'),D('1.2345')),
                       (D('.000001'),D('2.000001'),D('0'))):
            amounts=('20.123456','30','49.866544','.01')
            full=self.shares(totals,amounts)
            self.assertEqual(self.shares(totals,amounts[:-1]),full[:-1])
            for field,total in zip(fields,totals):
                cumulative=D(0)
                for index,amount in enumerate(amounts):
                    cumulative+=D(amount)
                    expected=total if index==len(amounts)-1 else (total*cumulative/D('100')).quantize(
                        _component_quantum(total),rounding=ROUND_HALF_UP)
                    self.assertEqual(sum(getattr(s,field) for s in full[:index+1]),expected)
                    self.assertGreaterEqual(getattr(full[index],field),0)
                self.assertEqual(sum(getattr(s,field) for s in full),total)

    def test_backdated_insertion_and_component_balance_not_forced(self):
        invoice=ArInvoiceRecognitionFacts('i',D('.02'),'EUR',None,D('.01'),D('.01'),D('.02'))
        first=ArAllocationRecognitionFacts('i','b','p',D('.01'),date(2026,2,1),'EUR')
        earlier=replace(first,allocation_id='a',payment_date=date(2026,1,1))
        before,=resolve_ar_recognition_events(invoice,(first,))
        after=resolve_ar_recognition_events(invoice,(first,earlier))
        self.assertEqual(before.net_amount_original,D('.01'))
        self.assertEqual(after[1].net_amount_original,D('0'))
        self.assertEqual(after[0].net_amount_original+after[0].vat_amount_original,D('.02'))
        self.assertEqual(after[0].amount_original,D('.01'))
        self.assertEqual(sum(e.net_amount_original+e.vat_amount_original for e in after),invoice.gross_amount)
