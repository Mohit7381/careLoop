import { Component, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly router = inject(Router);

  /**
   * The runs dashboard is the one screen styled in the Halodoc website
   * palette (light, #e0004d). The topbar lives in this shell rather than
   * inside the routed component, so it has to follow the route or it
   * would sit dark above a light page.
   */
  readonly lightShell = signal(false);

  constructor() {
    this.router.events
      .pipe(
        filter((e): e is NavigationEnd => e instanceof NavigationEnd),
        takeUntilDestroyed()
      )
      .subscribe((e) => this.lightShell.set(e.urlAfterRedirects.split('?')[0] === '/runs'));
  }
}
