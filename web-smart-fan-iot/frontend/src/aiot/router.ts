import { createRouter, createWebHistory } from 'vue-router';
import { currentUser, type Role } from './auth';
import { mayVisit } from './access';
import LoginPage from './pages/LoginPage.vue';

declare module 'vue-router' {
  interface RouteMeta {
    title?: string;
    roles?: Role[];
    public?: boolean;
  }
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/entrar',
      component: LoginPage,
      meta: { public: true, title: 'Entrar' },
    },
    {
      path: '/',
      component: () => import('./pages/OverviewPage.vue'),
      meta: { title: 'Visão geral' },
    },
    {
      path: '/usuarios',
      component: () => import('./pages/UsersPage.vue'),
      meta: { title: 'Usuários', roles: ['administrador'] },
    },
    {
      path: '/auditoria',
      component: () => import('./pages/AuditPage.vue'),
      meta: { title: 'Auditoria', roles: ['administrador'] },
    },
    {
      path: '/acesso-negado',
      component: () => import('./pages/DeniedPage.vue'),
      meta: { title: 'Acesso restrito' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
});

router.beforeEach((to) => {
  if (to.meta.public) return currentUser.value ? '/' : true;
  if (!currentUser.value)
    return { path: '/entrar', query: { next: to.fullPath } };
  return mayVisit(to.meta.roles, currentUser.value) ? true : '/acesso-negado';
});
