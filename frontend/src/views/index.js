import { createOperationsViews } from './operations-view';
import { createExtendedViews } from './extended-views';
import { createReportViews } from './report-view';
import { createForms } from './forms';
import { createMainViews } from './views';
export function createViews(model) {
  const views = {};
  Object.assign(views, createOperationsViews(model, views));
  Object.assign(views, createExtendedViews(model, views));
  Object.assign(views, createReportViews(model, views));
  Object.assign(views, createForms(model, views));
  Object.assign(views, createMainViews(model, views));
  return views;
}
