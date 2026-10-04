# Opened-deck fixtures

- `ezLoadPositionsB.nec` — Dan Maguire AC6LA's EZNEC/Pro+ 7.0 NEC-5-format
  network-connection test deck (two "parallel connected" `NT` loads on one
  virtual wire), copied verbatim. `test_opened_decks.py` holds the text
  route (`file_designs.builder_from_text`, what the workbench's "open a
  deck" uses) to the same outcome as the file route on it, whatever that
  outcome is: the deck's import is the subject of AK#1880, not of these tests.
