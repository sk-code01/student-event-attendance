import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Department } from '../models/department.model';
import { Paginated } from '../models/pagination.model';

@Injectable({ providedIn: 'root' })
export class DepartmentService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  /**
   * `all: true` asks for every row in one page instead of the default 20.
   *
   * These feed **dropdowns**, not paged tables, and a dropdown that silently
   * shows only the first twenty options is worse than one that fails: the
   * operator cannot tell that the option they wanted was left out. The API
   * caps `page_size` at 200, so this cannot be used to dump an unbounded set.
   *
   * Whether *inactive* rows are included is decided by the server from the
   * caller's role (Admin sees them, everyone else does not) — it was never
   * something this flag controlled.
   */
  list(params: { all?: boolean } = {}): Observable<Paginated<Department>> {
    let httpParams = new HttpParams();
    if (params.all) {
      httpParams = httpParams.set('page_size', '200');
    }
    return this.http.get<Paginated<Department>>(`${this.baseUrl}/departments/`, { params: httpParams });
  }

  create(payload: { name: string; code: string }): Observable<Department> {
    return this.http.post<Department>(`${this.baseUrl}/departments/`, payload);
  }
}
