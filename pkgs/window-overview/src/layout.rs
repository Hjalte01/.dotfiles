use crate::hypr::Snapshot;
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
    pub rect: Rect,
    pub canvas: Rect,
    pub cards: Vec<Card>,
}

pub fn matching(snapshot: &Snapshot, query: &str, workspace: Option<i64>) -> Vec<usize> {
    let words: Vec<_> = query.split_whitespace().map(str::to_lowercase).collect();
    snapshot
        .clients
        .iter()
        .enumerate()
        .filter(|(_, c)| {
            workspace.is_none_or(|w| c.workspace.id == w)
                && words.iter().all(|word| {
                    format!(
                        "{} {} {} {} {}",
                        c.app(),
                        c.title,
                        c.workspace.name,
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
    workspace: Option<i64>,
) -> Vec<Group> {
    if flat {
        return grid(indices.len(), area, 20., 1.6)
            .into_iter()
            .zip(indices)
            .map(|(rect, &index)| {
                let c = &snapshot.clients[index];
                Group {
                    id: c.workspace.id,
                    name: c.workspace.name.clone(),
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
            workspace.is_none_or(|id| id == w.id)
                && (indices
                    .iter()
                    .any(|&i| snapshot.clients[i].workspace.id == w.id)
                    || (snapshot.clients.iter().all(|c| c.workspace.id != w.id)
                        && workspace.is_none()
                        && indices.len() == snapshot.clients.len()))
        })
        .collect();
    // Occupied workspaces first, then empty ones, always independent of focus.
    workspaces.sort_by_key(|w| {
        (
            indices
                .iter()
                .all(|&i| snapshot.clients[i].workspace.id != w.id),
            w.name.parse::<u32>().unwrap_or(u32::MAX),
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
            let canvas = Rect::new(rect.x + 12., rect.y + 64., rect.w - 24., rect.h - 76.)
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
                name: w.name.clone(),
                monitor: monitor.name.clone(),
                rect,
                canvas,
                cards,
            }
        })
        .collect()
}

pub fn slot(snapshot: &Snapshot, index: usize) -> String {
    let c = &snapshot.clients[index];
    let position = snapshot.clients[..index]
        .iter()
        .filter(|other| other.workspace.id == c.workspace.id)
        .count()
        + 1;
    format!("{}.{}", c.workspace.name, position)
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
mod tests {
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
            clients: serde_json::from_value(v["clients"].clone()).unwrap(), monitor:"external".into(), active_address:"0x2".into()
        }).unwrap()
    }
    #[test]
    fn preserves_actual_positions_on_negative_origin_monitor() {
        let s = fixture();
        let g = arrange(&s, &[0, 1], Rect::new(0., 0., 1920., 1080.), false, None);
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
        let indices = matching(&s, "Right", None);
        assert_eq!(indices, vec![1]);
        let all = arrange(&s, &[0, 1], Rect::new(0., 0., 1920., 1080.), false, None);
        let filtered = arrange(&s, &indices, Rect::new(0., 0., 1920., 1080.), false, None);
        assert_eq!(filtered[0].cards[0].number, 2);
        assert_eq!(filtered[0].cards[0].rect.x, all[0].cards[1].rect.x);
    }
    #[test]
    fn hidden_group_members_all_have_selectable_previews() {
        let mut s = fixture();
        s.clients[1].at = s.clients[0].at;
        let groups = arrange(&s, &[0, 1], Rect::new(0., 0., 1920., 1080.), false, None);
        assert_eq!(groups[0].cards.len(), 2);
        let a = &groups[0].cards[0];
        let b = &groups[0].cards[1];
        assert!(a.overlap && b.overlap);
        assert_eq!(a.rect.overlap(b.rect), 0.);
    }
}
