# Nyquist stability criterion example

Argument-first educational video for **Manim Dock usability assessment**.

**Protocol:** produce with [Manim Skill](../../.cursor/skills/manim-skill/SKILL.md) as plain ManimCE (**no Dock knowledge** in the script). Assess with Dock only afterward.

```bash
cd examples/nyquist_stability
manim -ql script.py \
  Scene1_StabilityAndOnePlusG Scene2_ArgumentStatement \
  Scene3_ArgumentGeometry Scene4_DContour \
  Scene5_ApplyOnePlusG Scene6_ShiftMinusOne \
  Scene7_NyquistImage Scene8_CountAndWhy
```

- [`plan.md`](./plan.md) — Phase 1 (approved pedagogy)
- [`script.py`](./script.py) — Skill Phase 2 (8 scene classes)

Assessment: [`docs/assessments/nyquist-stability-usability.md`](../../docs/assessments/nyquist-stability-usability.md).
