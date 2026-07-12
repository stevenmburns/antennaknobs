from antennaknobs.core import save_or_show
from unittest.mock import MagicMock


class MockedPlt:
    def __init__(self):
        self.savefig = MagicMock(return_value=None)
        self.show = MagicMock(return_value=None)
        self.close = MagicMock(return_value=None)
        self.gcf = MagicMock()


def test_save_or_show():
    plt = MockedPlt()
    save_or_show(plt, "/dev/null")
    plt.savefig.assert_not_called()
    plt.show.assert_not_called()
    plt.close.assert_called_with()

    plt = MockedPlt()
    save_or_show(plt, "foo.pdf")
    plt.savefig.assert_called_with("foo.pdf")
    plt.show.assert_not_called()
    plt.close.assert_called_with()

    plt = MockedPlt()
    save_or_show(plt, None)
    plt.savefig.assert_not_called()
    plt.show.assert_called_with()
    plt.close.assert_called_with()

    # The AntennaKNoBs brand tag is stamped on the figure on every path.
    text_call = plt.gcf.return_value.text.call_args
    assert "AntennaKNoBs" in text_call.args[2]
