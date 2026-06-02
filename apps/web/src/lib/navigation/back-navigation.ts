export type BackNavigationTarget = {
  href: string;
  label: string;
};

export function normalizePathname(pathname: string | null | undefined): string {
  if (!pathname || !pathname.startsWith("/") || pathname.startsWith("//")) {
    return "/dashboard";
  }

  const [withoutHash] = pathname.split("#", 1);
  const [withoutQuery] = withoutHash.split("?", 1);
  const normalized = withoutQuery.length > 1 ? withoutQuery.replace(/\/+$/, "") : withoutQuery;

  return normalized === "" ? "/" : normalized;
}

export function isInternalNavigationPath(pathname: string | null | undefined): pathname is string {
  return Boolean(pathname && pathname.startsWith("/") && !pathname.startsWith("//"));
}

export function getBackNavigationTarget(pathname: string | null | undefined): BackNavigationTarget {
  const currentPath = normalizePathname(pathname);

  if (currentPath === "/" || currentPath === "/dashboard") {
    return { href: "/dashboard", label: "Workspace home" };
  }

  if (currentPath === "/products") {
    return { href: "/dashboard", label: "Dashboard" };
  }

  if (currentPath === "/products/new") {
    return { href: "/products", label: "Products" };
  }

  if (currentPath === "/agents") {
    return { href: "/dashboard", label: "Dashboard" };
  }

  if (currentPath === "/agent-builder") {
    return { href: "/agents", label: "Agents" };
  }

  if (currentPath === "/recommendations") {
    return { href: "/dashboard", label: "Dashboard" };
  }

  const monitoringAgentsMatch = currentPath.match(/^\/products\/([^/]+)\/monitoring\/([^/]+)\/agents$/);
  if (monitoringAgentsMatch) {
    return { href: `/products/${monitoringAgentsMatch[1]}/monitoring`, label: "Monitoring" };
  }

  const uploadMappingMatch = currentPath.match(/^\/products\/([^/]+)\/uploads\/([^/]+)\/mapping$/);
  if (uploadMappingMatch) {
    return { href: `/products/${uploadMappingMatch[1]}/uploads`, label: "Uploads" };
  }

  const productWorkflowMatch = currentPath.match(/^\/products\/([^/]+)\/(uploads|monitoring)$/);
  if (productWorkflowMatch) {
    return { href: `/products/${productWorkflowMatch[1]}`, label: "Product profile" };
  }

  const productDetailMatch = currentPath.match(/^\/products\/([^/]+)$/);
  if (productDetailMatch) {
    return { href: "/products", label: "Products" };
  }

  const parentPath = currentPath.split("/").slice(0, -1).join("/");
  return { href: parentPath || "/dashboard", label: "Parent page" };
}
