_brand_tag = None


def _get_brand_tag():
    """Attribution tag stamped on every chart, resolved once per process."""
    global _brand_tag
    if _brand_tag is None:
        try:
            from importlib.metadata import version

            _brand_tag = f"AntennaKNoBs {version('antennaknobs')}"
        except Exception:
            _brand_tag = "AntennaKNoBs"
    return _brand_tag


def save_or_show(plt, fn):
    # Every CLI chart leaves through here, so this one fig.text is the whole
    # branding story: a small corner tag that survives screenshot sharing.
    plt.gcf().text(
        0.995,
        0.005,
        _get_brand_tag(),
        ha="right",
        va="bottom",
        fontsize=6.5,
        color="0.65",
    )

    if fn is not None:
        if fn != "/dev/null":
            plt.savefig(fn)
    else:
        plt.show()

    plt.close()
