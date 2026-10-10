import { newId } from "./id";
import { createApp, h, reactive, ref, shallowRef, type Component } from "vue";
import { VueFlow, Handle, Position, type Node, type Edge, type NodeChange, type Connection } from "@vue-flow/core";
import { Background } from "@vue-flow/background";
import { Controls } from "@vue-flow/controls";
import { MiniMap } from "@vue-flow/minimap";
import "@vue-flow/core/dist/style.css";
import "@vue-flow/core/dist/theme-default.css";
import "@vue-flow/controls/dist/style.css";
import "@vue-flow/minimap/dist/style.css";
import { attachAvailable, removeMember, type Group, type GroupMember, type MemberState } from "./group-model";

export function enclaveCanvas(root: HTMLElement, changed: () => void, action: (kind: "check" | "start" | "attach", member: GroupMember, workspace?: string) => void, inspect: (member: GroupMember) => void) {
  let group: Group;
  const nodes = shallowRef<Node[]>([]);
  const edges = shallowRef<Edge[]>([]);
  const states = reactive(new Map<string, MemberState>());
  const workspaces = reactive(new Map<string, string>());
  const busy = ref(false);
  function sync() {
    nodes.value = group.members.map((member) => ({ id: member.container_id, type: "container", position: { x: member.x, y: member.y }, data: { member } }));
    edges.value = group.edges.map((edge) => ({ ...edge, type: "smoothstep" }));
  }
  createApp({ setup() {
    return () => h(VueFlow as Component, {
      id: "manual-enclave", nodes: nodes.value, edges: edges.value,
      nodesDraggable: !busy.value, nodesConnectable: !busy.value, deleteKeyCode: null,
      minZoom: 0.2, maxZoom: 2, defaultViewport: { x: 30, y: 30, zoom: 1 },
      onNodeClick: ({ node }: { node: Node }) => inspect(node.data.member),
      onNodesChange: (changes: NodeChange[]) => {
        for (const change of changes) if (change.type === "position" && change.position) {
          const member = group.members.find((member) => member.container_id === change.id);
          if (member && (member.x !== change.position.x || member.y !== change.position.y)) { member.x = change.position.x; member.y = change.position.y; changed(); }
        }
      },
      onConnect: (connection: Connection) => {
        if (busy.value || connection.source === connection.target) return;
        group.edges.push({ id: newId(), source: connection.source, target: connection.target });
        sync(); changed();
      },
      onEdgeDoubleClick: ({ edge }: { edge: Edge }) => {
        if (busy.value) return;
        group.edges = group.edges.filter((item) => item.id !== edge.id); sync(); changed();
      },
    }, {
      default: () => [h(Background, { gap: 20, color: "#56604e" }), h(Controls, { showInteractive: false }), h(MiniMap, { pannable: true, zoomable: true, nodeColor: "#dba543" })],
      "node-container": ({ data }: { data: { member: GroupMember } }) => {
        const member = data.member;
        const state = states.get(member.container_id);
        const report = state?.report;
        const runtime = state?.state === "ready" ? report?.runtime.docker.container.state : state?.state ?? "unchecked";
        const identity = report?.context.identity;
        const available = report?.context.workspaces ?? [];
        const workspace = workspaces.get(member.container_id) ?? available[0]?.name ?? "";
        const button = (label: string, click: () => void, disabled = false) => h("button", { type: "button", class: "secondary nodrag nopan", disabled: disabled || busy.value, onClick: (event: Event) => { event.stopPropagation(); click(); } }, label);
        return h("article", { class: `enclave-node ${runtime === "running" ? "online" : ""}` }, [
          h(Handle, { type: "target", position: Position.Left }),
          h("small", member.instance ? `CONTAINER · ${member.instance}` : "CONTAINER · DEFAULT"),
          h("strong", member.label), h("span", { class: "node-state" }, runtime),
          h("p", identity ? `${identity.name} · v${identity.version}` : report ? "Default identity" : "Check to see identity"),
          ...(state?.error ? [h("p", { class: "node-error" }, state.error)] : []),
          h("select", { class: "nodrag nopan", value: workspace, disabled: !attachAvailable(state) || busy.value, "aria-label": `Workspace in ${member.label}`, onChange: (event: Event) => workspaces.set(member.container_id, (event.target as HTMLSelectElement).value) }, available.length ? available.map((ws) => h("option", { value: ws.name }, ws.name)) : [h("option", { value: "" }, "No workspace checked")]),
          h("div", { class: "node-actions" }, [button("Check", () => action("check", member)), button("Start", () => action("start", member), state?.state !== "ready" || !["exited", "created"].includes(report?.runtime.docker.container.state ?? "")), button("Attach", () => action("attach", member, workspace), !attachAvailable(state))]),
          button("Remove from enclave", () => { removeMember(group, member.container_id); states.delete(member.container_id); sync(); changed(); }),
          h(Handle, { type: "source", position: Position.Right }),
        ]);
      },
    });
  } }).mount(root);
  return {
    setGroup(value: Group, keepStates = false) { group = value; if (!keepStates) { states.clear(); workspaces.clear(); } sync(); },
    setState(id: string, state: MemberState) { states.set(id, state); },
    state(id: string) { return states.get(id); },
    setBusy(value: boolean) { busy.value = value; },
    sync,
  };
}
