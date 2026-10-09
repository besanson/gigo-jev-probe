-- Number top-level headings in pandoc's plain-text rendering exactly as LaTeX numbers the PDF
-- (gate G4's section anchors). Pandoc's plain writer ignores --number-sections, so the numbers
-- are added here: unnumbered headings are skipped and numbering stops at the \appendix block.
local n = 0
local in_appendix = false

function RawBlock(el)
  if el.text:match("\\appendix") then
    in_appendix = true
  end
end

function Header(el)
  if el.level ~= 1 or in_appendix or el.classes:includes("unnumbered") then
    return el
  end
  n = n + 1
  table.insert(el.content, 1, pandoc.Space())
  table.insert(el.content, 1, pandoc.Str(tostring(n)))
  return el
end

return {{traverse = "topdown", RawBlock = RawBlock, Header = Header}}
