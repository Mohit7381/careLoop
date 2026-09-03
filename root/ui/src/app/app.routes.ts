import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'runs', pathMatch: 'full' },
  {
    path: 'runs',
    loadComponent: () => import('./features/runs-dashboard/runs-dashboard.component').then((m) => m.RunsDashboardComponent),
  },
  {
    path: 'runs/:id',
    loadComponent: () => import('./features/run-detail/run-detail.component').then((m) => m.RunDetailComponent),
  },
  { path: '**', redirectTo: 'runs' },
];
