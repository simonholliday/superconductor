const panelRenderers = {};

export function registerPanel(id, renderFn) {
    panelRenderers[id] = renderFn;
}

export function getRenderer(id) {
    return panelRenderers[id] || null;
}
