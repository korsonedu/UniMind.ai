import { defineModule } from '@directus/extensions-sdk';
import ModuleRoot from '../ModuleRoot.vue';

export default defineModule({
  id: 'unimind-admin', name: 'UniMind', icon: 'school',
  routes: [{ path: '', component: ModuleRoot }],
});
