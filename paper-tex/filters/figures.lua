-- Pandoc filter for the LaTeX build of paper 6.
-- The manuscript links its figures as SVG under paper/figs/ (readable on GitHub); LaTeX cannot
-- include SVG, so the build converts each figure to PDF beside main.tex
-- (paper-tex/build_main_tex.py) and this filter points the image at that PDF by basename.
function Image(img)
  local base = img.src:match("([^/]+)%.svg$")
  if base then
    img.src = base .. ".pdf"
  end
  return img
end
