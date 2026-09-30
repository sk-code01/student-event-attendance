import { Component, input } from '@angular/core';

/**
 * Inline filled icons.
 *
 * Kept as inline SVG rather than an icon font or a package: they inherit
 * `currentColor` (so they theme for free), they add no network request, and
 * the set is small enough that a dependency would cost more than it saves.
 */
@Component({
  selector: 'app-icon',
  standalone: true,
  template: `
    <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true" focusable="false">
      @switch (name()) {
        @case ('grid') {
          <path d="M3 3h6v6H3V3zm8 0h6v6h-6V3zM3 11h6v6H3v-6zm8 0h6v6h-6v-6z" />
        }
        @case ('sliders') {
          <path d="M3 5h9a3 3 0 015.8 1H17a1 1 0 010 2h-.2A3 3 0 0112 7H3a1 1 0 010-2zm0 8h.2a3 3 0 015.6 0H17a1 1 0 010 2H8.8a3 3 0 01-5.6 0H3a1 1 0 010-2z" />
        }
        @case ('users') {
          <path d="M7 9a3 3 0 100-6 3 3 0 000 6zM2.5 17a4.5 4.5 0 019 0v1h-9v-1zM14 9a2.5 2.5 0 100-5 2.5 2.5 0 000 5zm-1.4 2.3A4.5 4.5 0 0118 15.5V18h-3.3v-1c0-1.7-.6-3.3-1.6-4.5l-.5-1.2z" />
        }
        @case ('building') {
          <path fill-rule="evenodd" d="M4 2a1 1 0 00-1 1v14a1 1 0 001 1h5v-3h2v3h5a1 1 0 001-1V3a1 1 0 00-1-1H4zm2 3h2v2H6V5zm6 0h2v2h-2V5zM6 9h2v2H6V9zm6 0h2v2h-2V9z" clip-rule="evenodd" />
        }
        @case ('calendar') {
          <path fill-rule="evenodd" d="M6 2a1 1 0 011 1v1h6V3a1 1 0 112 0v1h1a2 2 0 012 2v9a2 2 0 01-2 2H4a2 2 0 01-2-2V6a2 2 0 012-2h1V3a1 1 0 011-1zM4 8v7h12V8H4z" clip-rule="evenodd" />
        }
        @case ('clipboard') {
          <path fill-rule="evenodd" d="M8 2a2 2 0 00-2 2H5a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2V6a2 2 0 00-2-2h-1a2 2 0 00-2-2H8zm0 2h4v1H8V4zm-1 6h6a1 1 0 110 2H7a1 1 0 110-2zm0 4h4a1 1 0 110 2H7a1 1 0 110-2z" clip-rule="evenodd" />
        }
        @case ('route') {
          <path fill-rule="evenodd" d="M5 2a3 3 0 00-1 5.8V12a3 3 0 003 3h4.2a2 2 0 103.6-1.5A2 2 0 0012.2 13H7a1 1 0 01-1-1V7.8A3 3 0 005 2zm0 2a1 1 0 110 2 1 1 0 010-2zm10 11a1 1 0 110 2 1 1 0 010-2z" clip-rule="evenodd" />
        }
        @case ('trophy') {
          <path fill-rule="evenodd" d="M5 3a1 1 0 00-1 1v1H3a1 1 0 00-1 1 4 4 0 003.2 3.9A5 5 0 009 13.9V16H7a1 1 0 100 2h6a1 1 0 100-2h-2v-2.1a5 5 0 003.8-3.9A4 4 0 0018 6a1 1 0 00-1-1h-1V4a1 1 0 00-1-1H5zm-1 4h.1a3 3 0 00.5 1.6A2 2 0 014 7zm12 0a2 2 0 01-.6 1.6A3 3 0 0015.9 7H16z" clip-rule="evenodd" />
        }
        @case ('shield') {
          <path fill-rule="evenodd" d="M10 1.5l6 2.3V9c0 4-2.6 7.6-6 9.5C6.6 16.6 4 13 4 9V3.8l6-2.3z" clip-rule="evenodd" />
        }
        @case ('check-shield') {
          <path fill-rule="evenodd" d="M10 1.5l6 2.3V9c0 4-2.6 7.6-6 9.5C6.6 16.6 4 13 4 9V3.8l6-2.3zm3.2 5.8a1 1 0 00-1.4-1.4L9 8.8 7.9 7.7a1 1 0 10-1.4 1.4l1.8 1.8a1 1 0 001.4 0l3.5-3.6z" clip-rule="evenodd" />
        }
        @case ('chart') {
          <path d="M3 16a1 1 0 001 1h13a1 1 0 100-2H5V4a1 1 0 10-2 0v12zm4-2a1 1 0 001-1V9a1 1 0 10-2 0v4a1 1 0 001 1zm4 0a1 1 0 001-1V6a1 1 0 10-2 0v7a1 1 0 001 1zm4 0a1 1 0 001-1v-2a1 1 0 10-2 0v2a1 1 0 001 1z" />
        }
        @case ('document') {
          <path fill-rule="evenodd" d="M5 2a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7l-5-5H5zm6 1.5L15.5 8H12a1 1 0 01-1-1V3.5zM6 10h8a1 1 0 110 2H6a1 1 0 110-2zm0 4h5a1 1 0 110 2H6a1 1 0 110-2z" clip-rule="evenodd" />
        }
        @case ('pulse') {
          <path fill-rule="evenodd" d="M8.3 3.1a1 1 0 011 .7l2.4 8 1.3-3.2a1 1 0 01.93-.6H17a1 1 0 110 2h-2.4l-2.2 5.4a1 1 0 01-1.87-.09l-2.3-7.7-1.3 3.7a1 1 0 01-.94.67H3a1 1 0 010-2h2.3l2.05-5.9a1 1 0 01.95-.68z" clip-rule="evenodd" />
        }
        @case ('spark') {
          <path d="M10 1.5l1.7 4.5 4.5 1.7-4.5 1.7L10 14l-1.7-4.6L3.8 7.7l4.5-1.7L10 1.5zM15.5 12l.8 2.1 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.1z" />
        }
        @case ('bookmark') {
          <path fill-rule="evenodd" d="M5 3a2 2 0 012-2h6a2 2 0 012 2v14l-5-3-5 3V3z" clip-rule="evenodd" />
        }
        @case ('camera') {
          <path fill-rule="evenodd" d="M8 3a1 1 0 00-.9.55L6.4 5H4a2 2 0 00-2 2v8a2 2 0 002 2h12a2 2 0 002-2V7a2 2 0 00-2-2h-2.4l-.7-1.45A1 1 0 0012 3H8zm2 4a4 4 0 110 8 4 4 0 010-8zm0 2a2 2 0 100 4 2 2 0 000-4z" clip-rule="evenodd" />
        }
        @case ('briefcase') {
          <path fill-rule="evenodd" d="M8 2a2 2 0 00-2 2v1H4a2 2 0 00-2 2v8a2 2 0 002 2h12a2 2 0 002-2V7a2 2 0 00-2-2h-2V4a2 2 0 00-2-2H8zm0 2h4v1H8V4z" clip-rule="evenodd" />
        }
        @case ('bell') {
          <path d="M10 2a5 5 0 00-5 5v3.2l-1.3 2.3A1 1 0 004.6 14h10.8a1 1 0 00.87-1.5L15 10.2V7a5 5 0 00-5-5zM8 15.5a2 2 0 004 0H8z" />
        }
        @case ('menu') {
          <path fill-rule="evenodd" d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clip-rule="evenodd" />
        }
        @case ('close') {
          <path fill-rule="evenodd" d="M4.3 4.3a1 1 0 011.4 0L10 8.6l4.3-4.3a1 1 0 111.4 1.4L11.4 10l4.3 4.3a1 1 0 01-1.4 1.4L10 11.4l-4.3 4.3a1 1 0 01-1.4-1.4L8.6 10 4.3 5.7a1 1 0 010-1.4z" clip-rule="evenodd" />
        }
        @case ('sun') {
          <path fill-rule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm5.7 2.3a1 1 0 010 1.4l-.7.7a1 1 0 11-1.4-1.4l.7-.7a1 1 0 011.4 0zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zm-2.3 5.7a1 1 0 01-1.4 0l-.7-.7a1 1 0 111.4-1.4l.7.7a1 1 0 010 1.4zM10 16a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zm-5.7-.3a1 1 0 010-1.4l.7-.7a1 1 0 111.4 1.4l-.7.7a1 1 0 01-1.4 0zM4 10a1 1 0 01-1 1H2a1 1 0 110-2h1a1 1 0 011 1zm1.3-5.7a1 1 0 011.4 0l.7.7a1 1 0 01-1.4 1.4l-.7-.7a1 1 0 010-1.4zM10 6a4 4 0 100 8 4 4 0 000-8z" clip-rule="evenodd" />
        }
        @case ('moon') {
          <path d="M16.3 12.2A7 7 0 017.8 3.7a7 7 0 108.5 8.5z" />
        }
        @case ('monitor') {
          <path fill-rule="evenodd" d="M3 4a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2h-3v2h2a1 1 0 110 2H6a1 1 0 110-2h2v-2H5a2 2 0 01-2-2V4zm2 0v8h10V4H5z" clip-rule="evenodd" />
        }
        @case ('search') {
          <path fill-rule="evenodd" d="M9 3.5a5.5 5.5 0 103.4 9.8l3.4 3.4a1 1 0 001.4-1.4l-3.4-3.4A5.5 5.5 0 009 3.5zM5.5 9a3.5 3.5 0 117 0 3.5 3.5 0 01-7 0z" clip-rule="evenodd" />
        }
        @case ('user') {
          <path fill-rule="evenodd" d="M10 9a3.5 3.5 0 100-7 3.5 3.5 0 000 7zm-6 8a6 6 0 1112 0v1H4v-1z" clip-rule="evenodd" />
        }
        @case ('key') {
          <path fill-rule="evenodd" d="M13 2a5 5 0 00-4.8 6.4L2.3 14.3a1 1 0 00-.3.7V18a1 1 0 001 1h3a1 1 0 001-1v-1h1a1 1 0 001-1v-1h1a1 1 0 00.7-.3l1-1A5 5 0 1013 2zm1.5 3a1.5 1.5 0 110 3 1.5 1.5 0 010-3z" clip-rule="evenodd" />
        }
        @case ('logout') {
          <path fill-rule="evenodd" d="M3 4a2 2 0 012-2h5a1 1 0 110 2H5v12h5a1 1 0 110 2H5a2 2 0 01-2-2V4zm10.3 2.3a1 1 0 011.4 0l3 3a1 1 0 010 1.4l-3 3a1 1 0 01-1.4-1.4L14.6 11H9a1 1 0 110-2h5.6l-1.3-1.3a1 1 0 010-1.4z" clip-rule="evenodd" />
        }
        @case ('chevron-left') {
          <path fill-rule="evenodd" d="M12.7 4.3a1 1 0 010 1.4L8.4 10l4.3 4.3a1 1 0 01-1.4 1.4l-5-5a1 1 0 010-1.4l5-5a1 1 0 011.4 0z" clip-rule="evenodd" />
        }
        @default {
          <circle cx="10" cy="10" r="7" />
        }
      }
    </svg>
  `,
  styles: [':host { display: inline-grid; place-items: center; } svg { width: 100%; height: 100%; }'],
})
export class IconComponent {
  readonly name = input.required<string>();
}
