import { createApp } from 'vue';
async function mountApp() {
  if (import.meta.env.VITE_APP_MODE === 'aiot') {
    const [{ default: App }, { router }] = await Promise.all([
      import('./aiot/App.vue'),
      import('./aiot/router'),
      import('./aiot/style.css'),
    ]);
    const app = createApp(App).use(router);
    await router.isReady();
    app.mount('#app');
  } else {
    const [{ default: App }] = await Promise.all([
      import('./App.vue'),
      import('./style.css'),
    ]);
    createApp(App).mount('#app');
  }
}
void mountApp();
