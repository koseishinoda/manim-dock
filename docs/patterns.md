# Pattern targets

Educational idioms Manim Dock optimizes:

| ID | Pattern | UI help | Code-owned |
|----|---------|---------|------------|
| P01 | Title / hook card | place, timing | wording |
| P02 | Definition block | place, buff | content / helper |
| P03 | Step list reveal | buff, lag_ratio | item text |
| P04 | Equation + emphasize | place, timing | LaTeX parts |
| P05 | Derivation chain | spacing, run_time | MathTex / matching |
| P06 | Two-column layout | gutter, columns | column contents |
| P07 | Brace / underline callout | place, timing | label text / target |
| P08 | NumberPlane / Axes intro | scale, timing | ranges / graphs |
| P09 | Side-by-side compare (vs) | gutter, timing | card contents |
| P10 | Succession beat | run_time / waits | which animations |
| P11 | Progressive build / cleanup | reorder, waits | what exists |
| P12 | Sections / chapters | outline, skip | section names |
| P15 | Extract to library | after extract: place/time | API design |

**Rule:** observe/assist `VGroup` composition; never author deep grouping in the GUI.
