"""
 Copyright (C) 2020 Marcin Rybacki

 This file is part of QuantLib, a free-software/open-source library
 for financial quantitative analysts and developers - http://quantlib.org/

 QuantLib is free software: you can redistribute it and/or modify it
 under the terms of the QuantLib license.  You should have received a
 copy of the license along with this program; if not, please email
 <quantlib-dev@lists.sf.net>. The license is also available online at
 <http://quantlib.org/license.shtml>.

 This program is distributed in the hope that it will be useful, but WITHOUT
 ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
 FOR A PARTICULAR PURPOSE.  See the license for more details.
"""

import unittest
import QuantLib as ql

from typing import List, Tuple


EPSILON = 1.e-9

# Hypothetical market data
EUR_ZERO_RATES = [(ql.Period(1, ql.Days), 0.0048),
                  (ql.Period(1, ql.Years), 0.0048),
                  (ql.Period(2, ql.Years), 0.00475),
                  (ql.Period(3, ql.Years), 0.005),
                  (ql.Period(5, ql.Years), 0.0055),
                  (ql.Period(10, ql.Years), 0.007)]

EUR_BEI_SWAP_RATES = [(ql.Period(1, ql.Years), 0.0301),
                      (ql.Period(2, ql.Years), 0.0299),
                      (ql.Period(3, ql.Years), 0.0305),
                      (ql.Period(5, ql.Years), 0.0315),
                      (ql.Period(10, ql.Years), 0.0355)]

# TODO: Include source.
EU_FIXING_DATA = [(ql.Date(1, ql.April, 2018), 103.11),
                  (ql.Date(1, ql.May, 2018), 103.64),
                  (ql.Date(1, ql.June, 2018), 103.76),
                  (ql.Date(1, ql.July, 2018), 103.41),
                  (ql.Date(1, ql.August, 2018), 103.58)]

CAL = ql.TARGET()

DAY_COUNTER = ql.ActualActual()

BDC = ql.ModifiedFollowing

VALUATION_DATE = CAL.adjust(ql.Date(10, ql.September, 2018))

OBSERVATION_LAG = ql.Period(3, ql.Months)


def create_inflation_helper(
        reference_date,
        inflation_data,
        inflation_index,
        discount_curve_handle,
        observation_lag=OBSERVATION_LAG,
        calendar=CAL,
        business_day_convention=BDC,
        day_counter=DAY_COUNTER):
    maturity = CAL.advance(reference_date, inflation_data[0])
    quote = ql.QuoteHandle(ql.SimpleQuote(inflation_data[1]))
    return ql.ZeroCouponInflationSwapHelper(
        quote,
        observation_lag,
        maturity,
        calendar,
        business_day_convention,
        day_counter,
        inflation_index,
        discount_curve_handle)


def build_nominal_term_structure(
        reference_date,
        nominal_data):
    nominal_dc = ql.Actual365Fixed()
    dates = [CAL.advance(reference_date, x[0]) for x in nominal_data]
    rates = [x[1] for x in nominal_data]
    return ql.ZeroCurve(dates, rates, nominal_dc)


def build_hicp_index(
        fixing_data,
        inflation_crv_handle,
        interpolated=False):
    index = ql.EUHICP(interpolated, inflation_crv_handle)
    for x in fixing_data:
        # force override in case of multiple use
        index.addFixing(x[0], x[1], True)

    return index


SEASONAL = {ql.January: 1.0, ql.February: 1.01, ql.March: 1.011,
            ql.April: 1.009, ql.May: 1.008, ql.June: 1.012,
            ql.July: 1.0078, ql.August: 1.006,
            ql.September: 1.0085, ql.October: 1.0096,
            ql.November: 1.0067, ql.December: 1.0055}


def construct_seasonality(evaluation_date):
    frequency = ql.Monthly
    seasonality_base_date = ql.Date(1, ql.January, evaluation_date.year())
    factors = list(SEASONAL.values())
    return ql.MultiplicativePriceSeasonality(
        seasonality_base_date, frequency, factors)


def get_seasonality_factor(d):
    return SEASONAL[d.month()]


def build_inflation_term_structure(
        reference_date,
        zero_coupon_data,
        inflation_index,
        nominal_term_structure_handle,
        observation_lag=OBSERVATION_LAG,
        include_seasonality=False):
    helpers = [create_inflation_helper(reference_date,
                                       x,
                                       inflation_index,
                                       nominal_term_structure_handle)
               for x in zero_coupon_data]
    base_zero_rate = zero_coupon_data[0][1]
    cpi_term_structure = ql.PiecewiseZeroInflation(
        reference_date,
        CAL,
        DAY_COUNTER,
        observation_lag,
        inflation_index.frequency(),
        inflation_index.interpolated(),
        base_zero_rate,
        nominal_term_structure_handle,
        helpers)
    if include_seasonality:
        seasonality = construct_seasonality(reference_date)
        cpi_term_structure.setSeasonality(seasonality)
    return cpi_term_structure


def create_inflation_swap(
        index,
        start_date,
        end_date,
        rate,
        observation_lag=OBSERVATION_LAG,
        nominal=1.e6,
        payer=ql.ZeroCouponInflationSwap.Payer):
    return ql.ZeroCouponInflationSwap(
        payer,
        nominal,
        start_date,
        end_date,
        CAL,
        BDC,
        DAY_COUNTER,
        rate,
        index,
        observation_lag)


def interpolate_historic_index(
        idx, fixing_date, observation_lag=OBSERVATION_LAG):
    f_d = ql.Date(1, fixing_date.month(), fixing_date.year())
    s_d = ql.Date.endOfMonth(fixing_date) + 1
    slope = (fixing_date - f_d) / (
        (s_d + observation_lag) - (f_d + observation_lag))
    return idx.fixing(f_d) + slope * (
        idx.fixing(s_d) - idx.fixing(f_d))


class InflationTest(unittest.TestCase):
    def setUp(self):
        ql.Settings.instance().setEvaluationDate(VALUATION_DATE)
        self.inflation_ts_handle = ql.RelinkableZeroInflationTermStructureHandle()
        self.nominal_ts_handle = ql.RelinkableYieldTermStructureHandle()
        self.nominal_ts_handle.linkTo(
            build_nominal_term_structure(VALUATION_DATE, EUR_ZERO_RATES))
        self.discount_engine = ql.DiscountingSwapEngine(self.nominal_ts_handle)

    def test_par_swap_pricing_fom_indexation_without_seasonality(self):
        """Testing pricing of par inflation swap for First-Of-Month indexation"""

        # Inflation curve handle
        inflation_idx = build_hicp_index(
            EU_FIXING_DATA, self.inflation_ts_handle)
        inflation_ts = build_inflation_term_structure(
            VALUATION_DATE,
            EUR_BEI_SWAP_RATES,
            inflation_idx,
            self.nominal_ts_handle)
        self.inflation_ts_handle.linkTo(inflation_ts)

        # Create par inflation swap
        zciis = create_inflation_swap(
            inflation_idx,
            VALUATION_DATE,
            CAL.advance(VALUATION_DATE, ql.Period(10, ql.Years)),
            0.0355)
        zciis.setPricingEngine(self.discount_engine)
        npv = zciis.NPV()

        # Check whether swap prices to par
        fail_msg = """ Failed to price zero coupon inflation swap to par:
                            index: {inflation_idx}
                            start date : {start_date}
                            end date: {end_date}
                            observation lag: {observation_lag}
                            npv: {npv}
                            expected npv: {expected_npv}
                            tolerance: {tolerance}
                   """.format(inflation_idx=inflation_idx.familyName(),
                              start_date=zciis.startDate(),
                              end_date=zciis.maturityDate(),
                              observation_lag=OBSERVATION_LAG,
                              npv=npv,
                              expected_npv=0.0,
                              tolerance=EPSILON)
        self.assertTrue(
            abs(npv < EPSILON),
            msg=fail_msg)

    def test_inflation_leg_payment_fom_indexation_without_seasonality(self):
        """Testing inflation leg payment for First-Of-Month indexation"""
        # Inflation curve handle
        inflation_idx = build_hicp_index(
            EU_FIXING_DATA, self.inflation_ts_handle)
        inflation_ts = build_inflation_term_structure(
            VALUATION_DATE,
            EUR_BEI_SWAP_RATES,
            inflation_idx,
            self.nominal_ts_handle)
        self.inflation_ts_handle.linkTo(inflation_ts)

        zciis = create_inflation_swap(
            inflation_idx,
            VALUATION_DATE,
            CAL.advance(VALUATION_DATE, ql.Period(10, ql.Years)),
            0.0355)
        zciis.setPricingEngine(self.discount_engine)

        inflation_cf = ql.as_indexed_cashflow(
            zciis.inflationLeg()[0])
        # Obtaining base index for the inflation swap
        swap_base_d = inflation_cf.baseDate()
        swap_base_index = inflation_idx.fixing(swap_base_d)
        # Replicate fixing projection
        fixing_d = inflation_cf.fixingDate()
        ts_base_d = inflation_ts.baseDate()
        ts_base_index = inflation_idx.fixing(ts_base_d)
        # Apply FOM indexation rule
        effective_fixing_d = ql.Date(
            1, fixing_d.month(), fixing_d.year())
        fraction = inflation_ts.dayCounter().yearFraction(
            ts_base_d, effective_fixing_d)
        t = inflation_ts.timeFromReference(effective_fixing_d)
        zero_rate = inflation_ts.zeroRate(t)
        expected_fixing = ts_base_index * (
            1.0 + zero_rate)**fraction

        expected_inflation_leg_payment = (
            expected_fixing / swap_base_index - 1.0) * inflation_cf.notional()
        actual_inflation_leg_payment = inflation_cf.amount()

        fail_msg = """ Failed to replicate inflation leg payment
                       for First-Of-Month indexation:
                            index: {inflation_idx}
                            start date : {start_date}
                            end date: {end_date}
                            observation lag: {observation_lag}
                            inflation leg payment: {actual_payment}
                            replicated payment: {expected_payment}
                            tolerance: {tolerance}
                   """.format(inflation_idx=inflation_idx.familyName(),
                              start_date=zciis.startDate(),
                              end_date=zciis.maturityDate(),
                              observation_lag=OBSERVATION_LAG,
                              actual_payment=actual_inflation_leg_payment,
                              expected_payment=expected_inflation_leg_payment,
                              tolerance=EPSILON)
        self.assertAlmostEquals(
            first=actual_inflation_leg_payment,
            second=expected_inflation_leg_payment,
            delta=EPSILON,
            msg=fail_msg)

    def test_swap_base_fixing_linear_indexation_without_seasonality(self):
        """Testing swap base fixing for linear indexation"""

        inflation_idx = build_hicp_index(
            EU_FIXING_DATA, self.inflation_ts_handle, interpolated=True)
        inflation_ts = build_inflation_term_structure(
            VALUATION_DATE,
            EUR_BEI_SWAP_RATES,
            inflation_idx,
            self.nominal_ts_handle)
        self.inflation_ts_handle.linkTo(inflation_ts)

        # Create inflation swap
        zciis = create_inflation_swap(
            inflation_idx,
            ql.Date(24, ql.August, 2018),
            ql.Date(24, ql.August, 2023),
            0.032)
        zciis.setPricingEngine(self.discount_engine)

        inflation_cf = ql.as_indexed_cashflow(
            zciis.inflationLeg()[0])

        swap_base_dt = inflation_cf.baseDate()
        swap_base_fixing = inflation_idx.fixing(swap_base_dt)
        expected_swap_base_index = interpolate_historic_index(
            inflation_idx, swap_base_dt)

        fail_msg = """ Failed to replicate inflation swap base index fixing
                       for linear indexation:
                            index: {inflation_idx}
                            start date : {start_date}
                            end date: {end_date}
                            observation lag: {observation_lag}
                            base index fixing: {base_index}
                            replicated base index fixing: {expected_base_index}
                            tolerance: {tolerance}
                   """.format(inflation_idx=inflation_idx.familyName(),
                              start_date=zciis.startDate(),
                              end_date=zciis.maturityDate(),
                              observation_lag=OBSERVATION_LAG,
                              base_index=swap_base_fixing,
                              expected_base_index=expected_swap_base_index,
                              tolerance=EPSILON)

        self.assertAlmostEquals(
            first=swap_base_fixing,
            second=expected_swap_base_index,
            delta=EPSILON,
            msg=fail_msg)

    def test_inflation_curve_base_fixing(self):
        """Testing inflation curve base fixing"""

        inflation_idx = build_hicp_index(
            EU_FIXING_DATA, self.inflation_ts_handle, interpolated=True)
        inflation_ts = build_inflation_term_structure(
            VALUATION_DATE,
            EUR_BEI_SWAP_RATES,
            inflation_idx,
            self.nominal_ts_handle)
        self.inflation_ts_handle.linkTo(inflation_ts)
        curve_base_dt = inflation_ts.baseDate()
        curve_base_fixing = inflation_idx.fixing(curve_base_dt)
        expected_curve_base_fixing = interpolate_historic_index(
            inflation_idx, curve_base_dt)

        fail_msg = """ Failed to replicate inflation curve base index fixing
                       for linear indexation:
                            index: {inflation_idx}
                            inflation curve base date : {base_date}
                            inflation curve base fixing: {base_fixing}
                            expected base fixing: {expected_base_fixing}
                            tolerance: {tolerance}
                   """.format(inflation_idx=inflation_idx.familyName(),
                              base_date=curve_base_dt,
                              base_fixing=curve_base_fixing,
                              expected_base_fixing=expected_curve_base_fixing,
                              tolerance=EPSILON)

        self.assertAlmostEquals(
            first=curve_base_fixing,
            second=expected_curve_base_fixing,
            msg=fail_msg,
            delta=EPSILON)

    def test_inflation_leg_payment_linear_indexation_without_seasonality(self):
        """Testing inflation leg payment for linear indexation"""

        inflation_idx = build_hicp_index(
            EU_FIXING_DATA, self.inflation_ts_handle, interpolated=True)
        inflation_ts = build_inflation_term_structure(
            VALUATION_DATE,
            EUR_BEI_SWAP_RATES,
            inflation_idx,
            self.nominal_ts_handle)
        self.inflation_ts_handle.linkTo(inflation_ts)

        # Create inflation swap
        zciis = create_inflation_swap(
            inflation_idx,
            ql.Date(24, ql.August, 2018),
            ql.Date(24, ql.August, 2023),
            0.032)
        zciis.setPricingEngine(self.discount_engine)

        inflation_cf = ql.as_indexed_cashflow(
            zciis.inflationLeg()[0])
        # Replicate projected swap fixing
        # Apply linear indexation rule
        fixing_d = inflation_cf.fixingDate()
        fraction = inflation_ts.dayCounter().yearFraction(
            inflation_ts.baseDate(), fixing_d)
        t = inflation_ts.timeFromReference(fixing_d)
        zero_rate = inflation_ts.zeroRate(t)

        curve_base_fixing = inflation_idx.fixing(inflation_ts.baseDate())
        expected_fixing = curve_base_fixing * (
            1.0 + zero_rate)**fraction

        # Assert inflation leg projected amount
        swap_base_fixing = inflation_idx.fixing(inflation_cf.baseDate())
        expected_inf_leg_payment = (
            expected_fixing / swap_base_fixing - 1.0) * inflation_cf.notional()
        actual_inf_leg_payment = inflation_cf.amount()

        fail_msg = """ Failed to replicate inflation leg payment
                       for linear indexation:
                            index: {inflation_idx}
                            start date : {start_date}
                            end date: {end_date}
                            observation lag: {observation_lag}
                            inflation leg payment: {actual_payment}
                            replicated payment: {expected_payment}
                            tolerance: {tolerance}
                   """.format(inflation_idx=inflation_idx.familyName(),
                              start_date=zciis.startDate(),
                              end_date=zciis.maturityDate(),
                              observation_lag=OBSERVATION_LAG,
                              actual_payment=actual_inf_leg_payment,
                              expected_payment=expected_inf_leg_payment,
                              tolerance=EPSILON)

        self.assertAlmostEquals(
            first=actual_inf_leg_payment,
            second=expected_inf_leg_payment,
            delta=EPSILON,
            msg=fail_msg)

    def test_linear_indexation_with_seasonality(self):
        """Testing inflation leg payment for linear indexation with seasonality"""

        inflation_idx = build_hicp_index(
            EU_FIXING_DATA, self.inflation_ts_handle, interpolated=True)
        inflation_ts = build_inflation_term_structure(
            VALUATION_DATE,
            EUR_BEI_SWAP_RATES,
            inflation_idx,
            self.nominal_ts_handle,
            include_seasonality=True)
        self.inflation_ts_handle.linkTo(inflation_ts)

        zciis = create_inflation_swap(
            inflation_idx,
            ql.Date(25, ql.July, 2018),
            ql.Date(25, ql.July, 2022),
            0.032)
        zciis.setPricingEngine(self.discount_engine)

        inflation_cf = ql.as_indexed_cashflow(
            zciis.inflationLeg()[0])

        # Obtaining base index for the inflation swap
        swap_base_d = inflation_cf.baseDate()
        swap_base_index = inflation_idx.fixing(swap_base_d)

        # Replicate fixing projection
        fixing_d = inflation_cf.fixingDate()
        ts_base_d = inflation_ts.baseDate()
        ts_base_index = inflation_idx.fixing(ts_base_d)

        # Apply linear indexation rule
        fraction = inflation_ts.dayCounter().yearFraction(
            ts_base_d, fixing_d)
        t = inflation_ts.timeFromReference(fixing_d)
        zero_rate = inflation_ts.zeroRate(t)

        # Calculate seasonality adjustment
        # Not that multiplicative seasonality is applied
        seasonality_b = get_seasonality_factor(ts_base_d)
        seasonality_f = get_seasonality_factor(fixing_d)

        expected_fixing = ts_base_index * (
            seasonality_f / seasonality_b) * (1.0 + zero_rate)**fraction

        expected_inf_leg_payment = (
            expected_fixing / swap_base_index - 1.0) * inflation_cf.notional()
        actual_inf_leg_payment = inflation_cf.amount()

        fail_msg = """ Failed to replicate inflation leg payment
                       for linear indexation and seasonality:
                            index: {inflation_idx}
                            start date : {start_date}
                            end date: {end_date}
                            observation lag: {observation_lag}
                            inflation leg payment: {actual_payment}
                            replicated payment: {expected_payment}
                            tolerance: {tolerance}
                   """.format(inflation_idx=inflation_idx.familyName(),
                              start_date=zciis.startDate(),
                              end_date=zciis.maturityDate(),
                              observation_lag=OBSERVATION_LAG,
                              actual_payment=actual_inf_leg_payment,
                              expected_payment=expected_inf_leg_payment,
                              tolerance=EPSILON)

        self.assertAlmostEquals(
            first=actual_inf_leg_payment,
            second=expected_inf_leg_payment,
            delta=EPSILON,
            msg=fail_msg)


if __name__ == '__main__':
    print('testing QuantLib ' + ql.__version__)
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(InflationTest, 'test'))
    unittest.TextTestRunner(verbosity=2).run(suite)
