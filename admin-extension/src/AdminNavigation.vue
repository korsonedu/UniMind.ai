<script setup lang="ts">
import { sections } from './navigation';
defineProps<{ active: string }>();
const groups = [...new Set(sections.map(section => section.group))];
</script>

<template>
  <nav class="um-management-navigation" aria-label="UniMind 管理导航">
    <div v-for="group in groups" :key="group" class="navigation-group">
      <p>{{ group }}</p>
      <router-link v-for="section in sections.filter(item => item.group === group)" :key="section.id"
        :to="`/unimind-admin/${section.id}`" :class="{ active: active === section.id }"
        :aria-current="active === section.id ? 'page' : undefined">
        <component :is="section.icon" :size="17" aria-hidden="true" />{{ section.name }}
      </router-link>
    </div>
  </nav>
</template>

<style scoped>
.um-management-navigation { padding: 18px 12px 30px; color: var(--theme--foreground, #20262b); font-size: 14px; }
.navigation-group + .navigation-group { margin-top: 22px; }
.navigation-group p { margin: 0 12px 7px; font-size: 11px; color: var(--theme--foreground-subdued, #68727d); }
.navigation-group a { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 5px; color: inherit; text-decoration: none; }
.navigation-group a:hover { background: var(--theme--background-accent, #f3f6f6); }
.navigation-group a.active { color: var(--theme--primary, #186e63); background: var(--theme--primary-background, #eaf3f0); font-weight: 600; }
.navigation-group a:focus-visible { outline: 2px solid var(--theme--primary, #186e63); outline-offset: 2px; }
</style>
