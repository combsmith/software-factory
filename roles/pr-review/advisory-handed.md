## The advisory reads

A reader of another model family has read this change before you. The Task's `advisory` says what became of each
reader's read: `completed`, or why not. A read that is missing is no reason to answer `incomplete`: review the change
as you would without it.

Each text of trust `advisory` whose id is the reader's Lens, a colon and a code is one finding of that reader, quoted
whole. Its severity, category, criterion and place are the reader's claims, as its words are, and it may be wrong.

- Check each one against the diff and the head before you judge it. Read what it names yourself.
- Where what you read shows the fault, raise the Finding as your own: on the changed lines that bring it in, with the
  category, severity and criterion the rubric gives it, never the reader's, and with `adopted_from` naming the
  reader's Lens and the surface `{"type": "annotation", "key": "<the text's id>"}`.
- Where you cannot confirm it in what you read, raise nothing for it. A reader's finding is never a reason to raise a
  Finding you did not check, nor to leave out one you found yourself.
