use crate::hypr::{self, Snapshot, Workspace};
use serde::Serialize;

#[derive(Clone, Copy, Debug, Default, Serialize)]
pub struct Rect {
    pub x: f32,
    pub y: f32,
    pub w: f32,
    pub h: f32,
}
impl Rect {
    pub fn new(x: f32, y: f32, w: f32, h: f32) -> Self {
        Self {
            x,
            y,
            w: w.max(1.),
            h: h.max(1.),
        }
    }
    pub fn contains(self, x: f32, y: f32) -> bool {
        x >= self.x && x < self.x + self.w && y >= self.y && y < self.y + self.h
    }
    pub fn inset(self, n: f32) -> Self {
        Self::new(self.x + n, self.y + n, self.w - 2. * n, self.h - 2. * n)
    }
    pub fn fit(self, w: f32, h: f32) -> Self {
        let scale = (self.w / w.max(1.)).min(self.h / h.max(1.));
        Self::new(
            (self.x + (self.w - w * scale) / 2.).round(),
            (self.y + (self.h - h * scale) / 2.).round(),
            (w * scale).round(),
            (h * scale).round(),
        )
    }
    fn overlap(self, other: Self) -> f32 {
        (self.x + self.w)
            .min(other.x + other.w)
            .sub(self.x.max(other.x))
            .max(0.)
            * (self.y + self.h)
                .min(other.y + other.h)
                .sub(self.y.max(other.y))
                .max(0.)
    }
}
use std::ops::Sub;

#[derive(Clone, Debug, Serialize)]
pub struct Card {
    pub index: usize,
    pub number: usize,
    pub slot: String,
    pub rect: Rect,
    pub overlap: bool,
}
#[derive(Clone, Debug, Serialize)]
pub struct Group {
    pub id: i64,
    pub name: String,
    pub monitor: String,
    pub set: Option<String>,
    pub rect: Rect,
    pub canvas: Rect,
    pub cards: Vec<Card>,
}

#[derive(Clone, Debug, Serialize)]
pub struct SetPanel {
    pub id: Option<String>,
    pub name: String,
    pub rect: Rect,
}

#[derive(Clone, Copy, Default)]
pub struct Scope {
    pub workspace: Option<i64>,
    pub all_sets: bool,
}
impl Scope {
    pub fn includes(&self, snapshot: &Snapshot, w: &Workspace) -> bool {
        self.workspace.is_none_or(|id| id == w.id)
            && (self.all_sets
                || snapshot
                    .workspace_set(&w.name)
                    .is_none_or(|s| s == snapshot.current_set))
    }
}

pub fn matching(snapshot: &Snapshot, query: &str, scope: Scope) -> Vec<usize> {
    let words: Vec<_> = query.split_whitespace().map(str::to_lowercase).collect();
    snapshot
        .clients
        .iter()
        .enumerate()
        .filter(|(_, c)| {
            scope.includes(snapshot, &c.workspace)
                && words.iter().all(|word| {
                    format!(
                        "{} {} {} {} {}",
                        c.app(),
                        c.title,
                        snapshot.context(&c.workspace),
                        c.class,
                        c.states()
                    )
                    .to_lowercase()
                    .contains(word)
                })
        })
        .map(|(i, _)| i)
        .collect()
}

pub fn arrange(
    snapshot: &Snapshot,
    indices: &[usize],
    area: Rect,
    flat: bool,
    scope: Scope,
) -> Vec<Group> {
    if flat {
        return grid(indices.len(), area, 20., 1.6)
            .into_iter()
            .zip(indices)
            .map(|(rect, &index)| {
                let c = &snapshot.clients[index];
                Group {
                    id: c.workspace.id,
                    name: hypr::workspace_label(&c.workspace.name).into(),
                    set: snapshot.workspace_set(&c.workspace.name).map(str::to_owned),
                    monitor: String::new(),
                    rect,
                    canvas: rect,
                    cards: vec![Card {
                        index,
                        number: index + 1,
                        slot: slot(snapshot, index),
                        rect: rect.inset(6.),
                        overlap: false,
                    }],
                }
            })
            .collect();
    }
    let mut workspaces: Vec<_> = snapshot
        .workspaces
        .iter()
        .filter(|w| {
            scope.includes(snapshot, w)
                && indices
                    .iter()
                    .any(|&i| snapshot.clients[i].workspace.id == w.id)
        })
        .collect();
    workspaces.sort_by_key(|w| {
        (
            snapshot
                .workspace_set(&w.name)
                .unwrap_or("shared")
                .to_owned(),
            hypr::workspace_label(&w.name)
                .parse::<u32>()
                .unwrap_or(u32::MAX),
            w.name.clone(),
        )
    });
    let bounds = grid(workspaces.len(), area, 24., 1.6);
    workspaces
        .into_iter()
        .zip(bounds)
        .map(|(w, rect)| {
            let clients: Vec<_> = indices
                .iter()
                .copied()
                .filter(|&i| snapshot.clients[i].workspace.id == w.id)
                .collect();
            let monitor = snapshot
                .monitors
                .iter()
                .find(|m| m.name == w.monitor)
                .or_else(|| {
                    clients.first().and_then(|&i| {
                        snapshot
                            .monitors
                            .iter()
                            .find(|m| m.id == snapshot.clients[i].monitor)
                    })
                })
                .unwrap_or(&snapshot.monitors[0]);
            let size = monitor.logical_size();
            let header = if rect.w < 320. || rect.h < 180. {
                36.
            } else {
                64.
            };
            let canvas = Rect::new(
                rect.x + 8.,
                rect.y + header,
                rect.w - 16.,
                rect.h - header - 8.,
            )
            .fit(size[0], size[1]);
            let scale = canvas.w / size[0];
            let raw: Vec<_> = clients
                .iter()
                .map(|&i| {
                    let c = &snapshot.clients[i];
                    Rect::new(
                        canvas.x + (c.at[0] - monitor.x) as f32 * scale,
                        canvas.y + (c.at[1] - monitor.y) as f32 * scale,
                        c.size[0] as f32 * scale,
                        c.size[1] as f32 * scale,
                    )
                })
                .collect();
            // Overlapping tabs/fullscreen windows remain together in their original
            // area, with separate previews so none is hidden behind another.
            let mut components: Vec<Vec<usize>> = Vec::new();
            for i in 0..raw.len() {
                let mut merged = vec![i];
                let mut j = 0;
                while j < components.len() {
                    if components[j].iter().any(|&a| {
                        merged.iter().any(|&b| {
                            raw[a].overlap(raw[b])
                                > 0.25 * (raw[a].w * raw[a].h).min(raw[b].w * raw[b].h)
                        })
                    }) {
                        merged.extend(components.remove(j));
                        j = 0;
                    } else {
                        j += 1;
                    }
                }
                components.push(merged);
            }
            let mut cards = Vec::new();
            for mut component in components {
                component.sort_unstable();
                let x = component
                    .iter()
                    .map(|&i| raw[i].x)
                    .fold(f32::INFINITY, f32::min);
                let y = component
                    .iter()
                    .map(|&i| raw[i].y)
                    .fold(f32::INFINITY, f32::min);
                let right = component
                    .iter()
                    .map(|&i| raw[i].x + raw[i].w)
                    .fold(0., f32::max);
                let bottom = component
                    .iter()
                    .map(|&i| raw[i].y + raw[i].h)
                    .fold(0., f32::max);
                let split = if component.len() > 1 {
                    grid(
                        component.len(),
                        Rect::new(x, y, right - x, bottom - y),
                        4.,
                        1.1,
                    )
                } else {
                    vec![raw[component[0]]]
                };
                for (&position, r) in component.iter().zip(split) {
                    let index = clients[position];
                    cards.push(Card {
                        index,
                        number: index + 1,
                        slot: slot(snapshot, index),
                        rect: r,
                        overlap: component.len() > 1,
                    });
                }
            }
            cards.sort_by_key(|c| c.index);
            Group {
                id: w.id,
                name: hypr::workspace_label(&w.name).into(),
                set: snapshot.workspace_set(&w.name).map(str::to_owned),
                monitor: monitor.name.clone(),
                rect,
                canvas,
                cards,
            }
        })
        .collect()
}

// All sets adds a shared boundary around each set in Workspaces view.
// Only sets represented by matching windows get a panel.
pub fn arrange_overview(
    snapshot: &Snapshot,
    indices: &[usize],
    area: Rect,
    flat: bool,
    scope: Scope,
) -> (Vec<SetPanel>, Vec<Group>) {
    if flat || !scope.all_sets || scope.workspace.is_some() {
        return (vec![], arrange(snapshot, indices, area, flat, scope));
    }
    let mut sets: Vec<_> = indices
        .iter()
        .map(|&i| {
            snapshot
                .workspace_set(&snapshot.clients[i].workspace.name)
                .map(str::to_owned)
        })
        .collect();
    sets.sort();
    sets.dedup();
    sets.sort_by_key(|id| {
        (
            id.as_deref() != Some(snapshot.current_set.as_str()),
            id.is_none(),
            id.as_deref()
                .map(|s| snapshot.set_name(s))
                .unwrap_or("Shared")
                .to_lowercase(),
            id.clone(),
        )
    });
    let bounds = grid(sets.len(), area, 24., 1.6);
    let mut panels = Vec::new();
    let mut groups = Vec::new();
    for (id, rect) in sets.into_iter().zip(bounds) {
        let children: Vec<_> = indices
            .iter()
            .copied()
            .filter(|&i| {
                snapshot.workspace_set(&snapshot.clients[i].workspace.name) == id.as_deref()
            })
            .collect();
        groups.extend(arrange(
            snapshot,
            &children,
            Rect::new(rect.x + 12., rect.y + 50., rect.w - 24., rect.h - 62.),
            flat,
            scope,
        ));
        let name = id
            .as_deref()
            .map(|s| snapshot.set_name(s))
            .unwrap_or("Shared")
            .to_owned();
        panels.push(SetPanel { id, name, rect });
    }
    (panels, groups)
}

pub fn slot(snapshot: &Snapshot, index: usize) -> String {
    let c = &snapshot.clients[index];
    let position = snapshot.clients[..index]
        .iter()
        .filter(|other| other.workspace.id == c.workspace.id)
        .count()
        + 1;
    format!("{}.{}", hypr::workspace_label(&c.workspace.name), position)
}

fn grid(count: usize, area: Rect, gap: f32, aspect: f32) -> Vec<Rect> {
    if count == 0 {
        return vec![];
    }
    let columns = (1..=count)
        .max_by(|&a, &b| {
            let score = |n: usize| {
                let rows = count.div_ceil(n);
                let w = (area.w - gap * (n - 1) as f32) / n as f32;
                let h = (area.h - gap * (rows - 1) as f32) / rows as f32;
                let usable = w.min((h - 76.).max(1.) * aspect);
                usable * usable / aspect
            };
            score(a).total_cmp(&score(b))
        })
        .unwrap();
    let rows = count.div_ceil(columns);
    let w = (area.w - gap * (columns - 1) as f32) / columns as f32;
    let h = ((area.h - gap * (rows - 1) as f32) / rows as f32).min(w / aspect + 76.);
    let top = area.y + (area.h - h * rows as f32 - gap * (rows - 1) as f32) / 2.;
    (0..count)
        .map(|i| {
            Rect::new(
                area.x + (i % columns) as f32 * (w + gap),
                top + (i / columns) as f32 * (h + gap),
                w,
                h,
            )
        })
        .collect()
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    fn fixture() -> Snapshot {
        serde_json::from_value(serde_json::json!({
            "monitors": [{"id":1,"name":"external","width":2560,"height":1440,"x":-2560,"y":0,"scale":1.0,"focused":true,"activeWorkspace":{"id":5,"name":"5"},"specialWorkspace":{"id":0,"name":""}}],
            "workspaces":[{"id":5,"name":"5","monitor":"external"}],
            "clients": [
                {"address":"0x1","mapped":true,"at":[-2548,38],"size":[1250,1390],"workspace":{"id":5,"name":"5"},"monitor":1,"class":"terminal","title":"Left"},
                {"address":"0x2","mapped":true,"at":[-1286,38],"size":[1250,1390],"workspace":{"id":5,"name":"5"},"monitor":1,"class":"terminal","title":"Right"}
            ],"monitor":"external","active_address":"0x2"
        })).map(|v: serde_json::Value| Snapshot {
            monitors: serde_json::from_value(v["monitors"].clone()).unwrap(),
            workspaces: serde_json::from_value(v["workspaces"].clone()).unwrap(),
            clients: serde_json::from_value(v["clients"].clone()).unwrap(), monitor:"external".into(), active_address:"0x2".into(), current_set:"current".into(), sets:vec![]
        }).unwrap()
    }
    pub(crate) fn sets_fixture() -> Snapshot {
        let mut s = fixture();
        s.sets = ["Current", "School", "Hobbies", "Fun"]
            .into_iter()
            .map(|name| hypr::WorkspaceSet {
                id: name.to_lowercase(),
                name: name.into(),
                monitors: Default::default(),
            })
            .collect();
        let mut parked = s.clients[0].clone();
        parked.address = "0x3".into();
        parked.workspace = Workspace {
            id: -10,
            name: "set:school:5".into(),
            monitor: "external".into(),
        };
        s.workspaces.push(parked.workspace.clone());
        s.clients.push(parked);
        s
    }
    #[test]
    fn scope_and_search_include_other_sets_only_when_requested() {
        let s = sets_fixture();
        assert_eq!(matching(&s, "", Scope::default()), vec![0, 1]);
        assert!(matching(&s, "School", Scope::default()).is_empty());
        let all = Scope {
            all_sets: true,
            ..Scope::default()
        };
        assert_eq!(matching(&s, "school workspace 5", all), vec![2]);
        assert_eq!(matching(&s, "", all), vec![0, 1, 2]);
        let groups = arrange(
            &s,
            &[0, 1],
            Rect::new(0., 0., 1920., 1080.),
            false,
            Scope::default(),
        );
        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0].set.as_deref(), Some("current"));
    }
    #[test]
    fn empty_workspaces_are_hidden_in_both_scopes_and_during_search() {
        let mut s = sets_fixture();
        for (id, name) in [(6, "6"), (-11, "set:school:6"), (-12, "special:empty")] {
            s.workspaces.push(Workspace {
                id,
                name: name.into(),
                monitor: "external".into(),
            });
        }
        let area = Rect::new(0., 0., 1920., 1080.);
        for all_sets in [false, true] {
            let scope = Scope {
                all_sets,
                ..Scope::default()
            };
            let indices = matching(&s, "", scope);
            let groups = arrange(&s, &indices, area, false, scope);
            assert_eq!(groups.len(), if all_sets { 2 } else { 1 });
            assert!(groups.iter().all(|g| !g.cards.is_empty()));
            assert!(arrange(&s, &[], area, false, scope).is_empty());
            assert_eq!(
                arrange(&s, &indices, area, true, scope).len(),
                indices.len()
            );
        }
        let scope = Scope {
            all_sets: true,
            ..Scope::default()
        };
        let indices = matching(&s, "School", scope);
        let filtered = arrange(&s, &indices, area, false, scope);
        assert_eq!(filtered.len(), 1);
        assert_eq!(filtered[0].cards[0].number, 3);
    }
    #[test]
    fn occupied_workspaces_keep_windows_inside_their_panels_at_each_screen_size() {
        let s = sets_fixture();
        let scope = Scope {
            all_sets: true,
            ..Scope::default()
        };
        for (width, height) in [(1920., 1200.), (2560., 1440.), (1366., 768.)] {
            let groups = arrange(
                &s,
                &[0, 1, 2],
                Rect::new(32., 164., width - 64., height - 242.),
                false,
                scope,
            );
            assert_eq!(groups.len(), 2);
            for g in &groups {
                for c in &g.cards {
                    assert_eq!(s.clients[c.index].workspace.id, g.id);
                    assert!(c.rect.x >= g.rect.x && c.rect.y >= g.rect.y);
                    assert!(c.rect.x + c.rect.w <= g.rect.x + g.rect.w + 1.);
                    assert!(c.rect.y + c.rect.h <= g.rect.y + g.rect.h + 1.);
                }
            }
        }
    }
    #[test]
    fn all_sets_groups_workspaces_and_keeps_window_results_flat() {
        let mut s = sets_fixture();
        let mut shared = s.clients[0].clone();
        shared.address = "0x4".into();
        shared.workspace = Workspace {
            id: -20,
            name: "special:shared".into(),
            monitor: "external".into(),
        };
        s.workspaces.push(shared.workspace.clone());
        s.clients.push(shared);
        // Empty workspaces and sets must not turn into empty panels.
        s.workspaces.push(Workspace {
            id: -21,
            name: "set:fun:1".into(),
            monitor: "external".into(),
        });
        let all = Scope {
            all_sets: true,
            ..Scope::default()
        };
        for flat in [false, true] {
            for (w, h) in [(1366., 768.), (1920., 1200.), (2560., 1440.)] {
                let area = Rect::new(32., 164., w - 64., h - 242.);
                let (panels, groups) = arrange_overview(&s, &[0, 1, 2, 3], area, flat, all);
                if flat {
                    assert!(panels.is_empty());
                    assert_eq!(groups.len(), 4);
                    assert_eq!(
                        groups
                            .iter()
                            .flat_map(|g| &g.cards)
                            .map(|c| c.number)
                            .collect::<Vec<_>>(),
                        vec![1, 2, 3, 4]
                    );
                    continue;
                }
                assert_eq!(
                    panels.iter().map(|p| p.name.as_str()).collect::<Vec<_>>(),
                    vec!["Current", "School", "Shared"]
                );
                for panel in &panels {
                    let children: Vec<_> = groups.iter().filter(|g| g.set == panel.id).collect();
                    assert!(!children.is_empty());
                    for group in children {
                        assert!(!group.cards.is_empty());
                        assert!(group.rect.x >= panel.rect.x && group.rect.y >= panel.rect.y + 49.);
                        assert!(group.rect.x + group.rect.w <= panel.rect.x + panel.rect.w + 0.1);
                        assert!(group.rect.y + group.rect.h <= panel.rect.y + panel.rect.h + 0.1);
                        for card in &group.cards {
                            assert_eq!(card.number, card.index + 1);
                            assert_eq!(
                                s.workspace_set(&s.clients[card.index].workspace.name),
                                panel.id.as_deref()
                            );
                        }
                    }
                }
            }
            let area = Rect::new(0., 0., 1920., 1080.);
            let (panels, groups) = arrange_overview(&s, &[2], area, flat, all);
            assert_eq!(panels.len(), if flat { 0 } else { 1 });
            if !flat {
                assert_eq!(panels[0].name, "School");
            }
            assert_eq!(groups.len(), 1);
            assert_eq!(groups[0].cards[0].number, 3);
            assert!(arrange_overview(&s, &[], area, flat, all).0.is_empty());
            assert!(arrange_overview(&s, &[0, 1], area, flat, Scope::default())
                .0
                .is_empty());
            assert!(arrange_overview(
                &s,
                &[2],
                area,
                flat,
                Scope {
                    workspace: Some(-10),
                    ..all
                }
            )
            .0
            .is_empty());
        }
    }
    #[test]
    fn preserves_actual_positions_on_negative_origin_monitor() {
        let s = fixture();
        let g = arrange(
            &s,
            &[0, 1],
            Rect::new(0., 0., 1920., 1080.),
            false,
            Scope::default(),
        );
        assert_eq!(g.len(), 1);
        assert!(g[0].cards[0].rect.x < g[0].cards[1].rect.x);
        assert!((g[0].cards[0].rect.y - g[0].cards[1].rect.y).abs() < 0.01);
        let ratio = (g[0].cards[1].rect.x - g[0].cards[0].rect.x) / g[0].canvas.w;
        assert!((ratio - 1262. / 2560.).abs() < 0.0001);
        assert_eq!(g[0].cards[0].slot, "5.1");
    }
    #[test]
    fn search_preserves_numbers_and_workspace_positions() {
        let s = fixture();
        let indices = matching(&s, "Right", Scope::default());
        assert_eq!(indices, vec![1]);
        let all = arrange(
            &s,
            &[0, 1],
            Rect::new(0., 0., 1920., 1080.),
            false,
            Scope::default(),
        );
        let filtered = arrange(
            &s,
            &indices,
            Rect::new(0., 0., 1920., 1080.),
            false,
            Scope::default(),
        );
        assert_eq!(filtered[0].cards[0].number, 2);
        assert_eq!(filtered[0].cards[0].rect.x, all[0].cards[1].rect.x);
    }
    #[test]
    fn hidden_group_members_all_have_selectable_previews() {
        let mut s = fixture();
        s.clients[1].at = s.clients[0].at;
        let groups = arrange(
            &s,
            &[0, 1],
            Rect::new(0., 0., 1920., 1080.),
            false,
            Scope::default(),
        );
        assert_eq!(groups[0].cards.len(), 2);
        let a = &groups[0].cards[0];
        let b = &groups[0].cards[1];
        assert!(a.overlap && b.overlap);
        assert_eq!(a.rect.overlap(b.rect), 0.);
    }
}
