"""
Nyquist stability criterion — Argument-first educational video.
"""

from __future__ import annotations

import numpy as np
from manim import *

PRIMARY = BLUE
CURVE = TEAL
ACCENT = YELLOW
ZERO_C = BLUE_C
WAIT = 0.35


def _box(label: str, color=WHITE) -> VGroup:
    rect = RoundedRectangle(width=1.8, height=0.9, corner_radius=0.08, color=color)
    txt = MathTex(label, font_size=36)
    txt.move_to(rect)
    return VGroup(rect, txt)


def _summing_junction(radius: float = 0.28) -> VGroup:
    c = Circle(radius=radius, color=WHITE)
    h = Line(LEFT * radius * 0.55, RIGHT * radius * 0.55, color=WHITE, stroke_width=2)
    v = Line(DOWN * radius * 0.55, UP * radius * 0.55, color=WHITE, stroke_width=2)
    minus = MathTex("-", font_size=22).next_to(c, DOWN, buff=0.05)
    return VGroup(c, h, v, minus)


class Scene1_StabilityAndOnePlusG(Scene):
    """Typical loop → unity → define stability → zeros of 1+G → count bridge."""

    def construct(self):
        title = Text("When is the closed loop stable?", font_size=40)
        title.to_edge(UP)
        self.play(Write(title), run_time=1.5)
        self.add_subcaption("A typical feedback system has a controller and a plant.", duration=2.5)

        summer = _summing_junction().shift(LEFT * 3.2)
        c_block = _box("C(s)", PRIMARY).shift(LEFT * 1.1)
        p_block = _box("P(s)", PRIMARY).shift(RIGHT * 1.3)
        y_dot = Dot(RIGHT * 3.4, radius=0.04)
        arr_r = Arrow(LEFT * 4.6, summer.get_left(), buff=0.05, stroke_width=3)
        arr_e = Arrow(summer.get_right(), c_block.get_left(), buff=0.05, stroke_width=3)
        arr_u = Arrow(c_block.get_right(), p_block.get_left(), buff=0.05, stroke_width=3)
        arr_y = Arrow(p_block.get_right(), y_dot.get_center(), buff=0.05, stroke_width=3)
        fb_path = VMobject(stroke_width=3, color=GREY_B)
        fb_path.set_points_as_corners(
            [
                y_dot.get_center(),
                y_dot.get_center() + DOWN * 1.4,
                summer.get_center() + DOWN * 1.4,
                summer.get_bottom(),
            ]
        )
        lab_r = MathTex("r", font_size=28).next_to(arr_r, UP, buff=0.08)
        lab_y = MathTex("y", font_size=28).next_to(y_dot, UP, buff=0.12)
        lab_c = Text("Controller", font_size=18, color=GREY_B).next_to(c_block, UP, buff=0.12)
        lab_p = Text("Plant", font_size=18, color=GREY_B).next_to(p_block, UP, buff=0.12)
        typical = VGroup(
            summer, c_block, p_block, y_dot, arr_r, arr_e, arr_u, arr_y, fb_path, lab_r, lab_y, lab_c, lab_p
        )
        typical.next_to(title, DOWN, buff=0.55)
        self.play(FadeIn(typical, shift=UP * 0.1), run_time=1.4)
        self.wait(WAIT)

        self.add_subcaption("Pack the forward path into the open-loop G.", duration=2.2)
        g_block = _box("G(s)", CURVE)
        g_block.move_to((c_block.get_center() + p_block.get_center()) / 2)
        brace = Brace(VGroup(c_block, p_block), DOWN, color=CURVE)
        g_eq = MathTex(r"G(s)=C(s)P(s)", font_size=32, color=CURVE)
        g_eq.next_to(brace, DOWN, buff=0.15)
        self.play(Create(brace), Write(g_eq), run_time=1.0)
    
        self.wait(1.5)
        self.wait(WAIT)
        self.play(
            FadeOut(c_block),
            FadeOut(p_block),
            FadeOut(lab_c),
            FadeOut(lab_p),
            FadeOut(brace),
            FadeOut(arr_u),
            ReplacementTransform(g_eq, g_block),
            run_time=1.1,
        )
        arr_e2 = Arrow(summer.get_right(), g_block.get_left(), buff=0.05, stroke_width=3)
        arr_y2 = Arrow(g_block.get_right(), y_dot.get_center(), buff=0.05, stroke_width=3)
        self.play(FadeIn(arr_e2), FadeIn(arr_y2), FadeOut(arr_e), FadeOut(arr_y), run_time=0.6)

        self.add_subcaption("Unity feedback: closed-loop map T equals G over one-plus-G.", duration=2.5)
        t_eq = MathTex(r"T(s)=\frac{G(s)}{1+G(s)}", font_size=40)
        t_eq.to_edge(DOWN, buff=0.55)
        self.play(Write(t_eq), run_time=1.0)
        self.wait(WAIT)

        self.add_subcaption(
            "Stable means every pole of T lies in the open left half-plane.",
            duration=3.0,
        )
        keep = VGroup(g_block, arr_e2, arr_y2, arr_r, fb_path, lab_r, lab_y, summer, y_dot)
        self.play(
            FadeOut(keep),
            t_eq.animate.to_edge(UP, buff=0.9),
            FadeOut(title),
            run_time=1.0,
        )
        plane = ComplexPlane(
            x_range=[-3, 3, 1],
            y_range=[-2.5, 2.5, 1],
            x_length=6.5,
            y_length=4.5,
            background_line_style={"stroke_opacity": 0.35},
        ).add_coordinates()
        plane.shift(DOWN * 0.15)
        lhp = Polygon(
            plane.n2p(-3 - 2.5j),
            plane.n2p(0 - 2.5j),
            plane.n2p(0 + 2.5j),
            plane.n2p(-3 + 2.5j),
            color=GREEN,
            fill_opacity=0.18,
            stroke_opacity=0,
        )
        rhp = Polygon(
            plane.n2p(0 - 2.5j),
            plane.n2p(3 - 2.5j),
            plane.n2p(3 + 2.5j),
            plane.n2p(0 + 2.5j),
            color=RED,
            fill_opacity=0.14,
            stroke_opacity=0,
        )
        lhp_lab = Text("open LHP", font_size=22, color=GREEN).next_to(plane, LEFT, buff=0.2).shift(UP * 0.8)
        rhp_lab = Text("open RHP", font_size=22, color=RED).next_to(plane, RIGHT, buff=0.2).shift(UP * 0.8)
        stab = MathTex(
            r"\text{stable}\iff\text{all poles of }T\text{ in open LHP}",
            font_size=30,
        )
        stab.to_edge(DOWN, buff=0.4)
        self.play(Create(plane), FadeIn(lhp), FadeIn(rhp), FadeIn(lhp_lab), FadeIn(rhp_lab), run_time=1.4)
        self.play(Write(stab), run_time=1.1)
        self.wait(0.6)

        self.add_subcaption(
            "Poles of T are the zeros of one-plus-G. So stability means no right-half-plane zeros of one-plus-G.",
            duration=3.5,
        )
        link = MathTex(
            r"\text{poles of }T=\text{zeros of }1+G",
            font_size=32,
        )
        link.next_to(stab, UP, buff=0.25)
        concl = MathTex(
            r"\text{stable}\iff\text{no zeros of }1+G\text{ in open RHP}",
            font_size=30,
            color=ACCENT,
        )
        concl.move_to(stab)
        self.play(Write(link), run_time=1.0)
        self.wait(WAIT)
        self.play(TransformMatchingTex(stab, concl), run_time=1.0)
        self.wait(0.5)

        bridge = Text(
            "How to count those open-RHP zeros without solving 1+G(s)=0?",
            font_size=24,
            color=GREY_A,
        )
        bridge.to_edge(DOWN, buff=0.25)
        self.play(
            FadeOut(plane),
            FadeOut(lhp),
            FadeOut(rhp),
            FadeOut(lhp_lab),
            FadeOut(rhp_lab),
            FadeOut(t_eq),
            FadeOut(link),
            concl.animate.to_edge(UP, buff=1.0),
            FadeIn(bridge),
            run_time=1.1,
        )
        self.add_subcaption(
            "The question is how to count those zeros without solving the characteristic equation.",
            duration=3.0,
        )
        self.wait(1.2)
        self.play(*[FadeOut(m) for m in self.mobjects])


class Scene2_ArgumentStatement(Scene):
    def construct(self):
        title = Text("Argument principle", font_size=36)
        title.to_edge(UP)
        self.play(Write(title), run_time=0.9)
        self.add_subcaption(
            "The Argument principle: the contour integral of f-prime over f equals two-pi-i times Z minus P.",
            duration=3.5,
        )

        hyp = VGroup(
            Text("Meromorphic f inside / on a simple closed contour Γ", font_size=24),
            Text("No zeros or poles on Γ", font_size=24, color=GREY_B),
            Text("Orientation: counterclockwise (theorem form)", font_size=24, color=GREY_B),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.25)
        hyp.next_to(title, DOWN, buff=0.55)
        self.play(LaggedStart(*[FadeIn(x, shift=UP * 0.1) for x in hyp], lag_ratio=0.25), run_time=1.4)

        integral = MathTex(
            r"\frac{1}{2\pi i}\oint_{\Gamma}\frac{f'(s)}{f(s)}\,ds = Z - P",
            font_size=44,
        )
        integral.move_to(ORIGIN + DOWN * 0.35)
        gloss = MathTex(
            r"Z=\text{zeros (mult.)},\quad P=\text{poles (order)}",
            font_size=28,
            color=GREY_B,
        )
        gloss.next_to(integral, DOWN, buff=0.45)
        self.play(Write(integral), run_time=1.4)
        self.play(FadeIn(gloss), run_time=0.6)
        self.wait(1.0)
        self.play(*[FadeOut(m) for m in self.mobjects])


class Scene3_ArgumentGeometry(Scene):
    """Toy f(s)=s-1 on |s|=1.6 (encloses zero at 1): wind about 0 equals Z-P=1."""

    def construct(self):
        title = Text("Geometric meaning: winding about 0", font_size=32)
        title.to_edge(UP)
        self.play(Write(title), run_time=0.8)
        self.add_subcaption(
            "As s travels once around Gamma, f of s traces a curve. Its windings about zero equal Z minus P.",
            duration=3.5,
        )

        left = ComplexPlane(
            x_range=[-2, 2, 1],
            y_range=[-2, 2, 1],
            x_length=4.2,
            y_length=4.2,
        ).add_coordinates()
        right = ComplexPlane(
            x_range=[-2, 2, 1],
            y_range=[-2, 2, 1],
            x_length=4.2,
            y_length=4.2,
        ).add_coordinates()
        left.to_edge(LEFT, buff=0.35).shift(DOWN * 0.25)
        right.to_edge(RIGHT, buff=0.35).shift(DOWN * 0.25)
        lab_s = Text("s-plane", font_size=22, color=PRIMARY).next_to(left, UP, buff=0.12)
        lab_w = Text("w-plane", font_size=22, color=CURVE).next_to(right, UP, buff=0.12)
        self.play(Create(left), Create(right), FadeIn(lab_s), FadeIn(lab_w), run_time=1.2)

        # Radius 1.6 so the contour encloses the zero at s=1 (unit circle would not).
        radius = 1.6
        theta = ValueTracker(0)

        def s_point():
            t = theta.get_value()
            return left.n2p(radius * np.cos(t) + 1j * radius * np.sin(t))

        def w_point():
            t = theta.get_value()
            s = radius * np.exp(1j * t)
            w = s - 1
            return right.n2p(w.real + 1j * w.imag)

        gamma_path = ParametricFunction(
            lambda t: left.n2p(radius * np.cos(t) + 1j * radius * np.sin(t)),
            t_range=[0, TAU],
            color=PRIMARY,
            stroke_width=4,
        )
        image_path = ParametricFunction(
            lambda t: right.n2p((radius * np.cos(t) - 1) + 1j * radius * np.sin(t)),
            t_range=[0, TAU],
            color=CURVE,
            stroke_width=4,
        )
        zero_dot = Dot(left.n2p(1 + 0j), color=ZERO_C, radius=0.08)
        zero_lab = MathTex("1", font_size=24, color=ZERO_C).next_to(zero_dot, UR, buff=0.08)
        origin_w = Dot(right.n2p(0 + 0j), color=ACCENT, radius=0.07)

        self.play(Create(gamma_path), FadeIn(zero_dot), FadeIn(zero_lab), run_time=1.0)
        self.play(Create(image_path), FadeIn(origin_w), run_time=1.0)

        s_dot = Dot(color=WHITE, radius=0.07).move_to(s_point())
        w_dot = Dot(color=ACCENT, radius=0.07).move_to(w_point())
        s_dot.add_updater(lambda m: m.move_to(s_point()))
        w_dot.add_updater(lambda m: m.move_to(w_point()))
        self.add(s_dot, w_dot)
        self.play(theta.animate.set_value(TAU), run_time=3.5, rate_func=linear)
        s_dot.clear_updaters()
        w_dot.clear_updaters()

        result = MathTex(
            r"\frac{1}{2\pi}\Delta_{\Gamma}\arg f=\mathrm{wind}(f(\Gamma),0)=Z-P=1",
            font_size=28,
        )
        result.to_edge(DOWN, buff=0.3)
        toy = MathTex(r"f(s)=s-1,\ |s|=1.6,\ Z=1,\ P=0", font_size=26, color=GREY_B)
        toy.next_to(result, UP, buff=0.15)
        self.play(Write(toy), Write(result), run_time=1.3)
        self.wait(1.0)
        self.play(*[FadeOut(m) for m in self.mobjects])


class Scene4_DContour(Scene):
    def construct(self):
        title = Text("Nyquist D-contour (enclose the RHP)", font_size=32)
        title.to_edge(UP)
        self.play(Write(title), run_time=0.8)
        self.add_subcaption(
            "Enclose the right half-plane with the Nyquist D-contour—indent past poles on the axis.",
            duration=3.0,
        )

        plane = ComplexPlane(
            x_range=[-2, 4, 1],
            y_range=[-3, 3, 1],
            x_length=7,
            y_length=5.5,
        ).add_coordinates()
        plane.next_to(title, DOWN, buff=0.35)
        self.play(Create(plane), run_time=1.2)

        indent_r = 0.35
        big_r = 2.8

        def n2p(x, y):
            return plane.n2p(x + 1j * y)

        pts = []
        for th in np.linspace(-PI / 2, PI / 2, 40):
            pts.append(n2p(indent_r * np.cos(th + PI), indent_r * np.sin(th + PI)))
        for y in np.linspace(indent_r, big_r, 50):
            pts.append(n2p(0, y))
        for th in np.linspace(PI / 2, -PI / 2, 80):
            pts.append(n2p(big_r * np.cos(th), big_r * np.sin(th)))
        for y in np.linspace(-big_r, -indent_r, 50):
            pts.append(n2p(0, y))

        contour = VMobject(color=PRIMARY, stroke_width=4)
        contour.set_points_smoothly(pts)
        tip = Text("indent around jω-axis poles", font_size=22, color=GREY_B)
        tip.to_edge(DOWN, buff=0.35)
        note = MathTex(r"\text{interior}=\text{open RHP}", font_size=28, color=ACCENT)
        note.next_to(tip, UP, buff=0.2)

        self.play(Create(contour), run_time=2.2)
        self.play(FadeIn(tip), FadeIn(note), run_time=0.7)
        self.wait(1.0)
        self.play(*[FadeOut(m) for m in self.mobjects])


class Scene5_ApplyOnePlusG(Scene):
    def construct(self):
        title = Text("Apply Argument to f = 1 + G", font_size=32)
        title.to_edge(UP)
        self.play(Write(title), run_time=0.8)
        self.add_subcaption(
            "Set f equal to one-plus-G. Z counts closed-loop RHP poles; P counts open-loop ones.",
            duration=3.2,
        )

        f_eq = MathTex(r"f(s)=1+G(s)\quad\text{on }\Gamma=D", font_size=36)
        f_eq.next_to(title, DOWN, buff=0.45)
        self.play(Write(f_eq), run_time=1.0)

        dictionary = VGroup(
            MathTex(
                r"Z=\#\{\text{zeros of }1+G\text{ in }D\}=\text{closed-loop RHP poles}",
                font_size=28,
            ),
            MathTex(
                r"P=\#\{\text{poles of }1+G\text{ in }D\}=\text{open-loop RHP poles of }G",
                font_size=28,
            ),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.35)
        dictionary.next_to(f_eq, DOWN, buff=0.55)
        self.play(LaggedStart(*[Write(x) for x in dictionary], lag_ratio=0.35), run_time=1.8)

        relation = MathTex(
            r"\frac{1}{2\pi}\Delta_D\arg(1+G)=Z_{\mathrm{cl}}-P_{\mathrm{ol}}",
            font_size=36,
        )
        relation.next_to(dictionary, DOWN, buff=0.55)
        self.play(Write(relation), run_time=1.1)

        plant = MathTex(
            r"G(s)=\frac{1}{s(s+1)},\quad \text{poles at }0,-1\Rightarrow P=0\text{ (open RHP)}",
            font_size=28,
            color=GREY_B,
        )
        plant.to_edge(DOWN, buff=0.4)
        self.play(FadeIn(plant), run_time=0.7)
        self.wait(1.2)
        self.play(*[FadeOut(m) for m in self.mobjects])


class Scene6_ShiftMinusOne(Scene):
    def construct(self):
        title = Text("Shift: wind about 0 ↔ wind about −1", font_size=30)
        title.to_edge(UP)
        self.play(Write(title), run_time=0.8)
        self.add_subcaption(
            "Winding of one-plus-G around zero is the same as winding of G around minus one.",
            duration=3.0,
        )

        left = Axes(x_range=[-2, 2, 1], y_range=[-2, 2, 1], x_length=4, y_length=4)
        right = Axes(x_range=[-2, 2, 1], y_range=[-2, 2, 1], x_length=4, y_length=4)
        left.to_edge(LEFT, buff=0.5).shift(DOWN * 0.2)
        right.to_edge(RIGHT, buff=0.5).shift(DOWN * 0.2)
        l_lab = MathTex(r"1+G", font_size=28).next_to(left, UP, buff=0.15)
        r_lab = MathTex(r"G", font_size=28).next_to(right, UP, buff=0.15)

        c1 = Circle(radius=0.9, color=CURVE).move_to(left.c2p(0.4, 0.2))
        c2 = Circle(radius=0.9, color=CURVE).move_to(right.c2p(-0.6, 0.2))
        z0 = Dot(left.c2p(0, 0), color=ACCENT)
        zm1 = Dot(right.c2p(-1, 0), color=ACCENT)
        z0_lab = MathTex("0", font_size=24, color=ACCENT).next_to(z0, DL, buff=0.1)
        zm1_lab = MathTex("-1", font_size=24, color=ACCENT).next_to(zm1, DL, buff=0.1)

        self.play(Create(left), Create(right), FadeIn(l_lab), FadeIn(r_lab), run_time=1.0)
        self.play(Create(c1), FadeIn(z0), FadeIn(z0_lab), run_time=0.8)
        self.play(TransformFromCopy(c1, c2), FadeIn(zm1), FadeIn(zm1_lab), run_time=1.2)

        identity = MathTex(r"1+G(s)=0\;\Leftrightarrow\; G(s)=-1", font_size=34)
        identity.to_edge(DOWN, buff=0.45)
        self.play(Write(identity), run_time=1.0)
        self.wait(1.0)
        self.play(*[FadeOut(m) for m in self.mobjects])


def _nyquist_points(n: int = 400) -> np.ndarray:
    """G(jw)=1/(jw(jw+1)) for w>0, plus conjugate mirror."""
    w = np.logspace(-2.5, 2.5, n // 2)
    s = 1j * w
    g = 1.0 / (s * (s + 1.0))
    pts = np.column_stack([g.real, g.imag])
    mirror = np.column_stack([g.real[::-1], -g.imag[::-1]])
    return np.vstack([pts, mirror])


class Scene7_NyquistImage(Scene):
    def construct(self):
        title = Text("Nyquist plot = image of D under G", font_size=30)
        title.to_edge(UP)
        self.play(Write(title), run_time=0.8)
        self.add_subcaption(
            "The Nyquist plot is the image of that D-contour under G. Encirclements of minus one are Argument's winding.",
            duration=3.5,
        )

        axes = Axes(
            x_range=[-2.5, 1.5, 0.5],
            y_range=[-2, 2, 0.5],
            x_length=7.5,
            y_length=5.2,
            tips=False,
        )
        axes.next_to(title, DOWN, buff=0.3)
        x_lab = MathTex(r"\mathrm{Re}\,G", font_size=24).next_to(axes.x_axis, RIGHT, buff=0.1)
        y_lab = MathTex(r"\mathrm{Im}\,G", font_size=24).next_to(axes.y_axis, UP, buff=0.1)
        g_card = MathTex(r"G(s)=\frac{1}{s(s+1)}", font_size=28, color=GREY_B)
        g_card.to_corner(UR).shift(DOWN * 0.7)

        pts = _nyquist_points()
        pts = pts[pts[:, 0] > -2.4]
        curve = VMobject(color=CURVE, stroke_width=4)
        curve.set_points_smoothly([axes.c2p(x, y) for x, y in pts])

        crit = Dot(axes.c2p(-1, 0), color=ACCENT, radius=0.08)
        crit_lab = MathTex("-1", font_size=28, color=ACCENT).next_to(crit, UL, buff=0.1)

        self.play(Create(axes), FadeIn(x_lab), FadeIn(y_lab), FadeIn(g_card), run_time=1.0)
        self.play(Create(curve), run_time=2.2)
        self.play(FadeIn(crit), Write(crit_lab), run_time=0.7)
        self.wait(1.0)
        self.play(*[FadeOut(m) for m in self.mobjects])


class Scene8_CountAndWhy(Scene):
    def construct(self):
        title = Text("Convention, count, and why Nyquist works", font_size=30)
        title.to_edge(UP)
        self.play(Write(title), run_time=0.8)

        conv = MathTex(
            r"N:=\mathrm{wind}\bigl(G(D),-1\bigr),\qquad N=Z-P",
            font_size=34,
        )
        conv.next_to(title, DOWN, buff=0.45)
        self.play(Write(conv), run_time=1.1)
        self.add_subcaption(
            "For this G, N is zero and P is zero, so Z is zero—stable.",
            duration=2.8,
        )

        axes = Axes(
            x_range=[-2.5, 1.5, 0.5],
            y_range=[-2, 2, 0.5],
            x_length=5.5,
            y_length=3.8,
            tips=False,
        )
        axes.next_to(conv, DOWN, buff=0.35)
        pts = _nyquist_points()
        pts = pts[pts[:, 0] > -2.4]
        curve = VMobject(color=CURVE, stroke_width=3.5)
        curve.set_points_smoothly([axes.c2p(x, y) for x, y in pts])
        crit = Dot(axes.c2p(-1, 0), color=ACCENT, radius=0.07)
        self.play(Create(axes), Create(curve), FadeIn(crit), run_time=1.3)
        self.play(Indicate(crit, color=ACCENT), run_time=0.8)

        nums = MathTex(
            r"N=0,\quad P=0\quad\Rightarrow\quad Z=0\quad\Rightarrow\quad\text{stable}",
            font_size=32,
        )
        nums.to_edge(DOWN, buff=1.1)
        self.play(Write(nums), run_time=1.0)

        why = VGroup(
            Text("1. Argument on 1+G over D counts Z_cl − P_ol", font_size=24),
            Text("2. The Nyquist plot encodes that winding as encirclements of −1", font_size=24),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.2)
        why.to_edge(DOWN, buff=0.25)
        self.add_subcaption(
            "Nyquist works because Argument counts closed-loop poles as windings of G about minus one.",
            duration=3.5,
        )
        self.play(FadeIn(why), run_time=0.9)
        self.wait(1.4)
        self.play(*[FadeOut(m) for m in self.mobjects])
