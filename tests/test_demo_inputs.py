from scripts.collect_demo_inputs import feasibility


def test_loss_and_margin_must_both_fit():
    assert feasibility(2,1,.2,20,0,10)
    assert not feasibility(13.18,1,.2,20,0,10)
    assert not feasibility(2,10,.2,20,0,10)


def test_stopout_can_precede_stop_even_if_loss_below_equity():
    assert not feasibility(9.5,5,.2,20,0,10)
    assert not feasibility(8,1,.2,3,1,10)
    assert not feasibility(None,1,.2,20,0,10)
