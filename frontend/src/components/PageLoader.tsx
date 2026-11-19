// The shared skeleton in index.html can also paint before the callback's JavaScript loads.
export function PageLoader() {
  return <span data-workspace-loader hidden />;
}
