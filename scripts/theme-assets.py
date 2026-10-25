#!/usr/bin/env python3
"""Build an offline theme catalog and original 4K vector wallpaper collection."""
import json
from pathlib import Path
import random
import subprocess
import sys


WALLPAPERS = [
    ("alpine", "Alpine · mountain dusk"),
    ("flow", "Flow · color ribbons"),
    ("orbit", "Orbit · quiet solar system"),
    ("daybreak", "Daybreak · sunlit dunes"),
    ("lagoon", "Lagoon · turquoise coast"),
    ("bloom", "Bloom · pastel petals"),
    ("bauhaus", "Bauhaus · bold geometry"),
    ("spectrum", "Spectrum · chromatic wave"),
    ("botanical", "Botanical · sage garden"),
]


def mix(first, second, amount):
    """Blend sRGB colors for gentle palette accents on independent backgrounds."""
    channels = (round(int(first[i:i+2], 16) * (1 - amount) + int(second[i:i+2], 16) * amount)
                for i in (1, 3, 5))
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def canvas(background, definitions=""):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="3840" height="2160" viewBox="0 0 1920 1080">
    <defs>{definitions}</defs><path fill="{background}" d="M0 0h1920v1080H0z"/>'''


def wallpapers(p):
    b, s, a, blue, teal = (p[k] for k in ("base", "surface", "accent", "blue", "teal"))
    head = f'''<svg xmlns="http://www.w3.org/2000/svg" width="3840" height="2160" viewBox="0 0 1920 1080">
    <defs><linearGradient id="sky" x2="0" y2="1"><stop stop-color="{b}"/><stop offset="1" stop-color="{s}"/></linearGradient>
    <linearGradient id="ridge" x2="0" y2="1"><stop stop-color="{blue}"/><stop offset="1" stop-color="{b}"/></linearGradient>
    <linearGradient id="ribbon"><stop stop-color="{a}"/><stop offset="1" stop-color="{teal}"/></linearGradient>
    <radialGradient id="glow"><stop stop-color="{a}" stop-opacity=".2"/><stop offset="1" stop-color="{a}" stop-opacity="0"/></radialGradient></defs>
    <path fill="url(#sky)" d="M0 0h1920v1080H0z"/>'''
    rng = random.Random(42)
    stars = "".join(f'<circle cx="{rng.randrange(1920)}" cy="{rng.randrange(70, 580)}" r="{rng.uniform(.5, 1.6):.2f}" fill="{p["text"]}" opacity=".35"/>' for _ in range(110))
    yield "alpine", head + stars + f'''
    <ellipse cx="1330" cy="300" rx="440" ry="400" fill="url(#glow)"/>
    <circle cx="1330" cy="300" r="65" fill="{p['yellow']}" opacity=".85"/>
    <path d="M0 760 200 530 320 650 590 290 820 610 1050 440 1300 700 1570 420 1920 690V1080H0Z" fill="url(#ridge)" opacity=".45"/>
    <path d="m488 433 102-143 135 188-91-60-36 14-27-37-83 38" fill="{p['text']}" opacity=".35"/>
    <path d="M0 870 340 680 650 850 990 600 1300 870 1630 690 1920 810V1080H0Z" fill="{s}"/>
    <path d="M0 940Q420 810 940 930T1920 920V1080H0Z" fill="{b}"/>
    <path d="M0 998Q580 900 1050 1000T1920 990" fill="none" stroke="{a}" stroke-width="1" opacity=".3"/></svg>'''
    yield "flow", head + f'''
    <ellipse cx="1200" cy="550" rx="700" ry="550" fill="url(#glow)"/>
    <g fill="none" stroke-linecap="round">
    <path d="M-200 920C370 1250 600 200 1170 480S1850 900 2120 250" stroke="{s}" stroke-width="210"/>
    <path d="M-200 860C370 1190 600 140 1170 420S1850 840 2120 190" stroke="url(#ribbon)" stroke-width="72" opacity=".6"/>
    <path d="M-200 800C370 1130 600 80 1170 360S1850 780 2120 130" stroke="{blue}" stroke-width="14" opacity=".6"/>
    <path d="M-200 770C370 1100 600 50 1170 330S1850 750 2120 100" stroke="{teal}" stroke-width="2" opacity=".7"/>
    </g></svg>'''
    yield "orbit", head + f'''
    <ellipse cx="1260" cy="530" rx="650" ry="600" fill="url(#glow)"/>
    <g fill="none" stroke="{p['muted']}" opacity=".18">
    <circle cx="1260" cy="530" r="200"/><circle cx="1260" cy="530" r="320"/>
    <circle cx="1260" cy="530" r="440"/><circle cx="1260" cy="530" r="560"/></g>
    <circle cx="1260" cy="530" r="105" fill="url(#ribbon)"/>
    <circle cx="980" cy="375" r="24" fill="{blue}"/>
    <circle cx="1655" cy="723" r="38" fill="{p['orange']}"/>
    <circle cx="740" cy="320" r="10" fill="{teal}"/>
    <path d="M200 880h260m-260 14h90" stroke="{a}" opacity=".35"/></svg>'''

    # These compositions keep their own light/colorful art direction in every
    # app theme. Subtle palette accents tie them to the desktop without turning
    # their daylight skies into dark backgrounds.
    sand = mix("#dd9579", p["orange"], .16)
    yield "daybreak", canvas("#f7eddf", f'''
    <linearGradient id="sun" x2="0" y2="1"><stop stop-color="#f8ca83"/><stop offset="1" stop-color="#e88f72"/></linearGradient>
    <linearGradient id="sand" x2="0" y2="1"><stop stop-color="{sand}"/><stop offset="1" stop-color="#b86f66"/></linearGradient>''') + '''
    <circle cx="1330" cy="390" r="186" fill="url(#sun)"/>
    <circle cx="1330" cy="390" r="215" fill="none" stroke="#dfad87" opacity=".3"/>
    <path d="M0 680C300 650 540 450 860 530S1430 850 1920 520V1080H0Z" fill="#e7c7a9"/>
    <path d="M0 820C380 460 800 640 1090 755S1680 700 1920 590V1080H0Z" fill="url(#sand)"/>
    <path d="M0 820C380 460 800 640 1090 755S1680 700 1920 590" fill="none" stroke="#fff0d7" stroke-width="2" opacity=".7"/>
    <path d="M0 930C470 1050 750 710 1190 850S1690 990 1920 790V1080H0Z" fill="#875b60"/>
    <path d="M0 1030C500 850 880 1090 1260 990S1710 900 1920 940V1080H0Z" fill="#514850"/>
    <g fill="none" stroke="#f7dec2" opacity=".17">
    <path d="M70 887C400 700 675 759 895 802"/><path d="M50 902C390 722 680 780 880 818"/>
    <path d="M30 917C380 744 680 801 865 834"/></g></svg>'''

    ocean = mix("#55b9bd", teal, .15)
    yield "lagoon", canvas("#eaf7f1", f'''
    <linearGradient id="water" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#b6e8d7"/><stop offset=".5" stop-color="{ocean}"/><stop offset="1" stop-color="#287b98"/></linearGradient>
    <linearGradient id="beach" x2="0" y2="1"><stop stop-color="#fff5df"/><stop offset="1" stop-color="#ecd6b3"/></linearGradient>''') + '''
    <path d="M0 280C360 140 650 430 990 290S1580 130 1920 300V1080H0Z" fill="url(#water)"/>
    <path d="M-80 700C300 420 570 990 1020 660S1650 470 2010 670" fill="none" stroke="#d2f4e7" stroke-width="3" opacity=".45"/>
    <path d="M-50 820C270 430 650 1040 1110 770S1660 590 2000 760V1080H-50Z" fill="#9ed8c9"/>
    <path d="M-50 845C270 455 650 1065 1110 795S1660 615 2000 785V1080H-50Z" fill="url(#beach)"/>
    <path d="M-50 834C270 444 650 1054 1110 784S1660 604 2000 774" fill="none" stroke="#fffdf0" stroke-width="8" opacity=".85"/>
    <path d="M980 180h300m-210 14h330m-410 14h210" stroke="#fff" stroke-width="2" opacity=".4"/>
    <ellipse cx="1430" cy="913" rx="65" ry="19" fill="#c6b897" opacity=".35"/>
    <path d="M1370 901Q1390 850 1435 866Q1470 870 1492 901Z" fill="#80998b"/>
    <path d="M1370 901Q1390 850 1435 866L1449 901Z" fill="#b3bfa4"/>
    </svg>'''

    lavender = mix("#b9b1df", a, .18)
    yield "bloom", canvas("#f6f0f3", f'''
    <radialGradient id="halo"><stop stop-color="#e3d3ef"/><stop offset="1" stop-color="#f6f0f3"/></radialGradient>
    <linearGradient id="petal" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#fff6ed"/><stop offset=".45" stop-color="#e9c4d3"/><stop offset="1" stop-color="{lavender}"/></linearGradient>
    <linearGradient id="fold" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#fff9ef"/><stop offset=".6" stop-color="#e6bfd1"/><stop offset="1" stop-color="#a79bca"/></linearGradient>''') + '''
    <ellipse cx="1210" cy="570" rx="700" ry="570" fill="url(#halo)"/>
    <g transform="translate(1220 570) rotate(-14)">
    <path d="M0 180C-280 220-480-130-275-335C-50-520 160-160 0 180Z" fill="url(#petal)"/>
    <path d="M0 180C-200-70-85-470 180-365C440-260 240 90 0 180Z" fill="url(#fold)"/>
    <path d="M0 180C60-190 450-230 420 20C400 270 110 330 0 180Z" fill="url(#petal)"/>
    <path d="M0 180C-80-90-370-225-425 10C-480 250-140 340 0 180Z" fill="url(#fold)"/>
    <path d="M0 180C-160 10-260 300-35 345C205 390 290 70 0 180Z" fill="url(#petal)"/>
    <path d="M0 180C-80-25-90-160-55-250" fill="none" stroke="#fff9f2" stroke-width="2" opacity=".45"/>
    <path d="M0 180C140 100 260 10 300-65" fill="none" stroke="#fff9f2" stroke-width="2" opacity=".45"/>
    </g></svg>'''

    ink = mix("#263f53", blue, .12)
    yield "bauhaus", canvas("#f3e8d3") + f'''
    <circle cx="1330" cy="385" r="225" fill="#e9ae43"/>
    <path d="M940 900V530a240 240 0 0 1 480 0v370Z" fill="{ink}"/>
    <path d="M1040 900V540a140 140 0 0 1 280 0v360Z" fill="#f3e8d3"/>
    <path d="M1450 1020V670a180 180 0 0 1 360 0v350Z" fill="#cd5e43"/>
    <path d="M1550 1020V680a80 80 0 0 1 160 0v340Z" fill="#f3e8d3"/>
    <path d="M620 840h240v240H620Z" fill="#6d9690"/>
    <path d="M620 840a240 240 0 0 1 240 240H620Z" fill="#a9b7a0"/>
    <path d="M940 950h480v48H940Z" fill="#e9ae43"/>
    <g stroke="{ink}" stroke-width="3" opacity=".45">
    <path d="M240 310h240m-240 20h240m-240 20h240m-240 20h240m-240 20h240"/></g>
    <circle cx="1620" cy="240" r="22" fill="{ink}"/>
    </svg>'''

    violet = mix("#7044c9", a, .14)
    yield "spectrum", canvas("#24164e", f'''
    <linearGradient id="chroma" x1="0" y1="1" x2="1" y2="0"><stop stop-color="#31c6c4"/><stop offset=".25" stop-color="#5e74e5"/><stop offset=".52" stop-color="{violet}"/><stop offset=".76" stop-color="#eb719c"/><stop offset="1" stop-color="#ffd296"/></linearGradient>
    <linearGradient id="edge" x1="0" y1="1" x2="1" y2="0"><stop stop-color="#8ce9dc"/><stop offset=".5" stop-color="#e2b8ee"/><stop offset="1" stop-color="#fff1cc"/></linearGradient>
    <radialGradient id="aura"><stop stop-color="#b261b9" stop-opacity=".5"/><stop offset="1" stop-color="#24164e" stop-opacity="0"/></radialGradient>''') + '''
    <ellipse cx="1450" cy="270" rx="1050" ry="800" fill="url(#aura)"/>
    <path d="M-180 1140C300 1000 380 200 920 400S1450 1210 2110-170" fill="none" stroke="#130f39" stroke-width="260" opacity=".45"/>
    <path d="M-180 1090C300 950 380 150 920 350S1450 1160 2110-220" fill="none" stroke="url(#chroma)" stroke-width="225"/>
    <path d="M-180 1005C300 865 380 65 920 265S1450 1075 2110-305" fill="none" stroke="url(#edge)" stroke-width="3" opacity=".85"/>
    <path d="M-180 1030C300 890 380 90 920 290S1450 1100 2110-280" fill="none" stroke="url(#edge)" stroke-width="1" opacity=".3"/>
    </svg>'''

    sage = mix("#608b78", p["green"], .12)
    leaves = []
    for index, (x, y, angle, scale) in enumerate([
        (1120, 900, -26, 1.1), (1470, 1010, 17, 1.35),
        (1710, 970, 48, .95), (890, 1040, -58, .8),
    ]):
        color = [sage, "#385f56", "#8da78c", "#b1bc98"][index]
        leaves.append(f'<g transform="translate({x} {y}) rotate({angle}) scale({scale})" fill="{color}">')
        leaves.append('<path d="M0 220Q-18-170 0-540" fill="none" stroke="#52735e" stroke-width="4"/>')
        for level in range(5):
            y = -level * 95
            size = 1 - level * .1
            leaves.append(f'''<path transform="translate(0 {y}) scale({size})" d="M0 0C-115-5-170-85-153-130C-61-132-18-61 0 0Z"/>
            <path transform="translate(0 {y - 42}) scale({size})" d="M0 0C110-10 151-82 143-124C53-117 11-52 0 0Z"/>''')
        leaves.append('</g>')
    yield "botanical", canvas("#edf0df") + '''
    <circle cx="1335" cy="450" r="310" fill="#e1c589" opacity=".55"/>
    <path d="M0 1010Q650 880 1100 1000T1920 940V1080H0Z" fill="#dce3ce"/>
    ''' + "".join(leaves) + '</svg>'


def files(p):
    b, s, o, t, m, a = (p[k] for k in ("base", "surface", "overlay", "text", "muted", "accent"))
    yield "colors.json", json.dumps(p, indent=2) + "\n"
    yield "hyprland.conf", f"general:col.active_border = rgb({a[1:]})\ngeneral:col.inactive_border = rgb({o[1:]})\n"
    rofi = {"base":b, "surface":s, "foreground":t, "accent":a, "background":b,
            "lightbg":s, "lightfg":o, "blue":p['blue'], "red":p['red'],
            "background-color":b, "text-color":t, "border-color":a,
            "selected-normal-background":a, "selected-normal-foreground":b,
            "selected-active-background":a, "selected-active-foreground":b,
            "selected-urgent-background":p['red'], "selected-urgent-foreground":b}
    yield "colors.rasi", "* {\n" + "\n".join(f"  {key}: {value};" for key, value in rofi.items()) + "\n}\n"
    yield "colors.css", "\n".join(f"@define-color {key} {value};" for key, value in {"background":b, "foreground":t, "surface":s, "overlay":o, "muted":m, "accent":a, "error":p['red']}.items()) + "\n"
    # QPalette ColorRole order through Accent (Qt 6.6); Qt 5 reads its subset.
    roles = [t, s, o, o, b, s, t, t, t, b, b, b, a, b, p['blue'], p['pink'], s, b, t, t, m, a]
    active = ", ".join("#ff" + c[1:] for c in roles)
    disabled = ", ".join("#ff" + (m if i in (0, 6, 8) else c)[1:] for i, c in enumerate(roles))
    yield "qt.colors", f"[ColorScheme]\nactive_colors={active}\ninactive_colors={active}\ndisabled_colors={disabled}\n"
    ansi = [s, p['red'], p['green'], p['yellow'], p['blue'], p['pink'], p['teal'], t]
    yield "ghostty.conf", f"background = {b}\nforeground = {t}\ncursor-color = {a}\nselection-background = {a}\nselection-foreground = {b}\n" + "\n".join(f"palette = {i}={c}" for i, c in enumerate(ansi + [o] + ansi[1:])) + "\n"
    yield "mako.conf", f"background-color={b}\ntext-color={t}\nborder-color={a}\nprogress-color=over {s}\ninclude=~/.config/mako/base.conf\n"
    yield "gtk.css", f"@define-color theme_bg_color {b};\n@define-color theme_fg_color {t};\n@define-color theme_base_color {b};\n@define-color theme_text_color {t};\n@define-color theme_selected_bg_color {a};\n@define-color theme_selected_fg_color {b};\nwindow, dialog, popover, menu {{ background-color: {b}; color: {t}; }}\nheaderbar, toolbar {{ background-color: {s}; color: {t}; }}\nentry, textview, textview text {{ background-color: {s}; color: {t}; }}\n.view {{ background-color: {b}; color: {t}; }}\nselection, *:selected {{ background-color: {a}; color: {b}; }}\n"
    yield "gtk4.css", f"@define-color window_bg_color {b};\n@define-color window_fg_color {t};\n@define-color view_bg_color {b};\n@define-color view_fg_color {t};\n@define-color headerbar_bg_color {s};\n@define-color headerbar_fg_color {t};\n@define-color card_bg_color {s};\n@define-color popover_bg_color {s};\n@define-color popover_fg_color {t};\n@define-color accent_bg_color {a};\n@define-color accent_fg_color {b};\n@define-color accent_color {a};\n:root {{ --window-bg-color: {b}; --window-fg-color: {t}; --view-bg-color: {b}; --view-fg-color: {t}; --headerbar-bg-color: {s}; --headerbar-fg-color: {t}; --card-bg-color: {s}; --popover-bg-color: {s}; --popover-fg-color: {t}; --accent-bg-color: {a}; --accent-fg-color: {b}; --accent-color: {a}; }}\n"
    yield "dictation.css", f"window {{ background: transparent; }}\n.dictation-card {{ background: {b}; color: {t}; border: 1px solid {a}; border-radius: 14px; padding: 13px 16px; }}\n.dictation-status {{ font-weight: bold; font-size: 12px; color: {a}; }}\n.dictation-text {{ font-size: 14px; color: {t}; }}\n.dictation-detail {{ font-size: 10px; color: {m}; }}\n"
    yield "zathurarc", f"set default-bg '{b}'\nset default-fg '{t}'\nset statusbar-bg '{s}'\nset statusbar-fg '{t}'\nset inputbar-bg '{s}'\nset inputbar-fg '{t}'\nset highlight-color '{a}'\nset highlight-active-color '{p['yellow']}'\n"
    yield "tmux.conf", f"set -g status-style 'bg={b},fg={t}'\nset -g status-right-style 'bg={s},fg={t}'\nset -g pane-border-style 'fg={o}'\nset -g pane-active-border-style 'fg={a}'\nsetw -g window-status-style 'bg={b},fg={m}'\nsetw -g window-status-current-style 'bg={a},fg={b}'\nsetw -g window-status-format ' #I #W #F '\nset -g message-style 'bg={s},fg={t}'\nsetw -g mode-style 'bg={a},fg={b}'\n"
    yield "obsidian.css", f"body.theme-dark, body.theme-light {{ --background-primary: {b}; --background-primary-alt: {b}; --background-secondary: {s}; --background-secondary-alt: {s}; --background-modifier-border: {o}; --text-normal: {t}; --text-muted: {m}; --text-faint: {m}; --text-accent: {a}; --interactive-accent: {a}; --interactive-accent-hover: {p['pink']}; --text-on-accent: {b}; --color-accent: {a}; --link-color: {a}; --link-color-hover: {p['pink']}; --h1-color: {a}; --h2-color: {p['blue']}; --h3-color: {p['teal']}; }}\n"
    bt = {"main_bg":b, "main_fg":t, "title":a, "hi_fg":a, "selected_bg":s, "selected_fg":t, "inactive_fg":m, "graph_text":m, "meter_bg":o, "proc_misc":p['teal'], "cpu_box":a, "mem_box":p['green'], "net_box":p['blue'], "proc_box":p['pink'], "div_line":o}
    for prefix, color in [("temp",p['red']), ("cpu",p['blue']), ("free",p['green']), ("cached",p['teal']), ("available",p['green']), ("used",p['pink']), ("download",p['green']), ("upload",p['blue']), ("process",a)]:
        bt.update({prefix+"_start":s, prefix+"_mid":color, prefix+"_end":color})
    yield "btop.theme", "\n".join(f'theme[{k}]="{v}"' for k,v in bt.items()) + "\n"


def main():
    palettes = json.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    (out / "palettes.json").write_text(json.dumps(palettes, indent=2))
    (out / "wallpapers.json").write_text(json.dumps(WALLPAPERS, indent=2) + "\n")
    for key, p in palettes.items():
        dest = out / key
        dest.mkdir(exist_ok=True)
        for name, data in files(p):
            (dest / name).write_text(data)
        for name, svg in wallpapers(p):
            image = dest / f"{name}.svg"
            image.write_text(svg)
            subprocess.run(["resvg", str(image), str(image.with_suffix('.png'))], check=True)
            subprocess.run(["resvg", "--width", "480", str(image), str(dest / f"{name}-thumb.png")], check=True)


if __name__ == "__main__":
    main()
