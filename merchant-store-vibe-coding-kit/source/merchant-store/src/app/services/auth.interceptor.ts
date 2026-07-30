// AuthInterceptor is intentionally not registered.
// Authenticated backend calls are made through KeycloakService.get/post/delete,
// which refreshes tokens by calling estore-app /refresh before invoking APIs.
export {};
