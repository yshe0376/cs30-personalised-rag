from cs30.ui.math_markdown import format_math_markdown


def test_latex_delimiters_render_without_markdown_italics():
    text = r"Newton: \[\mathbf{F}_{\text{net}} = m\mathbf{a}\]. Then \(a = F_{net}/m\)."
    result = format_math_markdown(text)
    assert "$$\n" + r"\mathbf{F}_{\text{net}} = m\mathbf{a}" + "\n$$" in result
    assert r"$a = F_{net}/m$" in result
    assert r"\[" not in result


def test_existing_math_code_links_and_plain_prose_are_preserved():
    text = r"Keep $F_{net}=ma$, $$E=mc^2$$, `\(raw\)`, [source](url), cost 10 dollars."
    assert format_math_markdown(text) == text
    code = "```latex\n" + r"\[F=ma\]" + "\n```"
    assert format_math_markdown(code) == code


def test_detects_bracketed_latex_and_standalone_latex_equation():
    assert format_math_markdown(r"Answer (a = \frac{F}{m})") == r"Answer $a = \frac{F}{m}$"
    assert "$$" in format_math_markdown(r"\Delta U = Q - W")
    assert format_math_markdown("This is text (not a formula).") == "This is text (not a formula)."
