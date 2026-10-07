# Documents

## The CoA agent guide

A plain-language guide for someone who is not technical: what the agent is for, what each certificate is checked against, each step it takes, who decides pass or fail, and what it adds. Figures are from `coa-api/dataset/eval/results.md`.

| File                                         | What it is                                                                       |
| -------------------------------------------- | -------------------------------------------------------------------------------- |
| [coa-agent-guide.pdf](coa-agent-guide.pdf)   | 7 A4 pages, made from the HTML below                                             |
| [coa-agent-guide.docx](coa-agent-guide.docx) | The same guide for Word (A4); not opened in Word by its author                   |
| [coa-agent-guide.html](coa-agent-guide.html) | The source of the web page and of the PDF (a page fragment, not a full document) |

The web version was published as a private page; its source is the HTML file here.

## Rebuilding

The guide is in two places that have to be kept in step by hand: the HTML (which also makes the PDF) and `build/build-docx.js` (the Word file). If the evaluation is run again or the agent changes, update the figures in both, then rebuild:

```bash
# PDF, from the HTML
cd docs/build
uv run --with reportlab --with beautifulsoup4 python html-to-pdf.py ../coa-agent-guide.html ../coa-agent-guide.pdf

# Word
npm install --no-save docx
node build-docx.js ../coa-agent-guide.docx
```

Look at the PDF after building it (render a page with `pdftoppm`): the layout is computed, not previewed. The Word file needs opening in Word to check the table widths.
