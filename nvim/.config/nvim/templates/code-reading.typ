// Source is data, never evaluated as Typst markup.
#let data = json("source.json")
#set document(title: data.title)
#set page(
  paper: "a4",
  margin: (x: 16mm, top: 18mm, bottom: 18mm),
  header: text(size: 8pt, fill: luma(110), data.title),
  footer: context align(center, text(size: 8pt, fill: luma(110), counter(page).display("1 / 1", both: true))),
)
#set text(font: "DejaVu Sans Mono", size: 10pt, fill: rgb("24292e"), ligatures: false)
#set par(leading: 0.55em)
#show raw: set text(size: 10pt)
#let gutter = calc.max(4, str(data.first_line + data.source.split("\n").len()).len() + 1) * 1em
#show raw.line: it => {
  // Keep numbers outside the text area, including on wrapped lines.
  box(width: 0pt, {
    h(-gutter)
    box(width: gutter - 1em, align(right, text(fill: luma(150), str(data.first_line + it.number - 1))))
  })
  // Adjacent boxes allow even long identifiers to wrap without inserting
  // invisible characters into the searchable, copyable PDF text.
  show regex("[^\\s]+"): word => {
    for cluster in word.text.clusters() { box(cluster) }
  }
  it.body
}
#pad(left: gutter, raw(data.source, block: true, lang: data.language, tab-size: data.tab_size))
