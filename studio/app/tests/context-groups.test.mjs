import test from "node:test";
import assert from "node:assert/strict";
import { load } from "./helpers.mjs";

test("workspace grouping follows Git identity across different checkout folders", async () => {
  const { workspaceRepositoryGroups, checkoutLabel } = await load("context-model");
  const report = { context: { update_targets: [{ repository_id: "api", name: "api", path: "/source/api" }] } };
  const projects = [
    { name: "custom-login", path: "/one/login", kind: "git_worktree", branch: "feature/login", repository_id: "api", dirty: true },
    { name: "api", path: "/source/api", kind: "git_repository", branch: "main", repository_id: "api" },
    { name: "api", path: "/different/api", kind: "git_repository", repository_id: "other-api" },
    { name: "api", path: "/plain/api", kind: "directory" },
    { name: "api", path: "/unknown/api", kind: "git_worktree" },
  ];
  const groups = workspaceRepositoryGroups(report, projects);
  assert.equal(groups.length, 4);
  assert.equal(groups[0].name, "api");
  assert.equal(groups[0].path, "/source/api");
  assert.deepEqual(groups[0].projects, projects.slice(0, 2));
  assert.equal(groups[0].projects[0], projects[0]);
  assert.equal(checkoutLabel(projects[0]), "feature/login");
  assert.equal(checkoutLabel(projects[1]), "main");
  assert.equal(checkoutLabel(projects[4]), "Detached HEAD");
});

test("worktree-only groups use a source-free label and leave checkout names intact", async () => {
  const { workspaceRepositoryGroups } = await load("context-model");
  const projects = [
    { name: "api--login", path: "/trees/login", kind: "git_worktree", repository_id: "api" },
    { name: "api--fix", path: "/elsewhere/fix", kind: "git_worktree", repository_id: "api" },
  ];
  const groups = workspaceRepositoryGroups({ context: { update_targets: [] } }, projects);
  assert.equal(groups[0].name, "api");
  assert.equal(groups[0].projects[0].name, "api--login");
  assert.equal(groups[0].projects[1].path, "/elsewhere/fix");
});
