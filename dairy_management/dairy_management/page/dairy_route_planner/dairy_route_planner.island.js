import { mountVueIsland } from "@framework/ui/island";
import Page from "./dairy_route_planner.vue";

export const mount = (el, context) =>
    mountVueIsland(el, {
        ...context,
        component: Page,
    });
