//! Shared scientific-notation dictionary for dictation and its live preview.
use std::{env, fs, path::PathBuf};
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

#[derive(Debug)]
pub struct Rule {
    alias: String,
    canonical: String,
}

pub fn rules_from_tsv(tsv: &str) -> Result<Vec<Rule>> {
    let mut rules: Vec<Rule> = Vec::new();
    for (line_number, line) in tsv.lines().enumerate() {
        if line.trim().is_empty() || line.trim_start().starts_with('#') {
            continue;
        }
        let mut fields = line.split('\t');
        let canonical = fields.next().unwrap_or_default().trim();
        if canonical.is_empty() {
            return Err(format!("Empty spelling on dictionary line {}", line_number + 1).into());
        }
        for alias in std::iter::once(canonical).chain(fields.map(str::trim)) {
            if alias.is_empty() || !alias.is_ascii() {
                return Err(format!("Expected an ASCII alias on line {}", line_number + 1).into());
            }
            let alias = alias
                .split_whitespace()
                .collect::<Vec<_>>()
                .join(" ")
                .to_ascii_lowercase();
            if let Some(previous) = rules.iter().find(|rule| rule.alias == alias) {
                if previous.canonical != canonical {
                    return Err(format!("Conflicting spelling for alias '{alias}'").into());
                }
                continue;
            }
            rules.push(Rule {
                alias,
                canonical: canonical.to_string(),
            });
        }
    }
    rules.sort_by_key(|rule| std::cmp::Reverse(rule.alias.len()));
    Ok(rules)
}

pub fn load_rules() -> Result<Vec<Rule>> {
    let configured = env::var_os("DICTATION_TERMS").map(PathBuf::from);
    let config_home = env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .or_else(|| env::var_os("HOME").map(|home| PathBuf::from(home).join(".config")));
    let path = configured
        .clone()
        .or_else(|| config_home.map(|dir| dir.join("dictation/terms.tsv")));
    let contents = match path {
        Some(path) if configured.is_some() || path.exists() => fs::read_to_string(path)?,
        _ => include_str!("../terms.tsv").to_string(),
    };
    rules_from_tsv(&contents)
}

fn is_word(character: char) -> bool {
    character.is_alphanumeric() || character == '_'
}

fn match_alias(input: &str, alias: &str) -> Option<usize> {
    let mut offset = 0;
    for expected in alias.chars() {
        if expected == ' ' {
            let start = offset;
            while let Some(actual) = input[offset..].chars().next() {
                if !actual.is_whitespace() {
                    break;
                }
                offset += actual.len_utf8();
            }
            if start == offset {
                return None;
            }
        } else {
            let actual = input[offset..].chars().next()?;
            if !actual.eq_ignore_ascii_case(&expected) {
                return None;
            }
            offset += actual.len_utf8();
        }
    }
    if input[offset..].chars().next().is_some_and(is_word) {
        None
    } else {
        Some(offset)
    }
}

pub fn normalize(input: &str, rules: &[Rule]) -> String {
    let mut output = String::with_capacity(input.len());
    let mut offset = 0;
    let mut previous = None;
    while offset < input.len() {
        let matched = if previous.is_none_or(|character| !is_word(character)) {
            rules.iter().find_map(|rule| {
                match_alias(&input[offset..], &rule.alias).map(|length| (rule, length))
            })
        } else {
            None
        };
        if let Some((rule, length)) = matched {
            output.push_str(&rule.canonical);
            previous = input[..offset + length].chars().next_back();
            offset += length;
        } else {
            let character = input[offset..]
                .chars()
                .next()
                .expect("offset is before input end");
            output.push(character);
            offset += character.len_utf8();
            previous = Some(character);
        }
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    fn correct(text: &str) -> String {
        normalize(text, &rules_from_tsv(include_str!("../terms.tsv")).unwrap())
    }

    #[test]
    fn scientific_notation_in_english_and_danish() {
        assert_eq!(
            correct("Compare ddpm with IMF and improved mean flow."),
            "Compare DDPM with iMF and improved MeanFlow."
        );
        assert_eq!(
            correct("Vi sammenligner ddpm og imf med mean flow, så æøå bevares."),
            "Vi sammenligner DDPM og iMF med MeanFlow, så æøå bevares."
        );
    }

    #[test]
    fn spelled_letters_and_flexible_spacing() {
        assert_eq!(
            correct("D D P M, i  m\tf, dee dee pee em, eye em eff."),
            "DDPM, iMF, DDPM, iMF."
        );
        assert_eq!(
            correct("(D.D.P.M.) and I. M. F. use mean-flow."),
            "(DDPM.) and iMF. use MeanFlow."
        );
    }

    #[test]
    fn partially_grouped_acronyms_and_other_ml_notation() {
        assert_eq!(
            correct("DD PM, D DPM, I MF, IM F; ddim, sde, ode, vae, elbo, mse, cfg, jvp, vjp."),
            "DDPM, DDPM, iMF, iMF; DDIM, SDE, ODE, VAE, ELBO, MSE, CFG, JVP, VJP."
        );
        // DiT would collide with an ordinary Danish word, so it is not a rule.
        assert_eq!(
            correct("Det er dit arbejde og din model."),
            "Det er dit arbejde og din model."
        );
    }

    #[test]
    fn preserves_word_boundaries_punctuation_and_layout() {
        let text = "ddpmodel my_ddpm imformat æimf imfø 42imf\n\n‘ddpm’, imf's; (mean flow)!";
        assert_eq!(
            correct(text),
            "ddpmodel my_ddpm imformat æimf imfø 42imf\n\n‘DDPM’, iMF's; (MeanFlow)!"
        );
        assert_eq!(correct(""), "");
        assert_eq!(correct("  \n\t"), "  \n\t");
    }

    #[test]
    fn prefers_long_aliases() {
        let rules = rules_from_tsv("X\tone two\nY\tone\n").unwrap();
        assert_eq!(normalize("one two one", &rules), "X Y");
    }

    #[test]
    fn rejects_ambiguous_dictionaries() {
        assert!(rules_from_tsv("DDPM\tmodel\niMF\tMODEL\n").is_err());
        assert!(rules_from_tsv("DDPM\t\n").is_err());
        assert!(rules_from_tsv("DDPM\tddpm\tDDPM\n").is_ok());
    }

    #[test]
    fn applying_rules_twice_is_stable() {
        let original = "ddpm and I M F improve mean flow.";
        assert_eq!(correct(&correct(original)), correct(original));
    }
}
