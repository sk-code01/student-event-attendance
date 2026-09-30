import { ActivityRecord } from './activity.model';
import { AppNotification } from './notification.model';

/** One operational count. The backend decides which cards a role may see, so
 * the frontend renders whatever arrives rather than hard-coding a per-role
 * list that could drift out of step with the authorization rules. */
export interface DashboardCard {
  key: string;
  label: string;
  value: number;
  /** Internal Angular path. Never contains a query string. */
  route: string;
  /**
   * Query parameters for the link, kept separate from `route` because
   * `routerLink` given a bare string treats the whole thing as one path
   * segment and would encode a "?" instead of parsing it.
   */
  query?: Record<string, string>;
}

export interface Dashboard {
  role: string;
  cards: DashboardCard[];
  recent_activity: ActivityRecord[];
  recent_notifications: AppNotification[];
  unread_notifications: number;
}
