<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { X } from 'lucide-vue-next';
defineProps<{ title: string; busy?: boolean }>();
const emit = defineEmits<{ close: [] }>();
const element = ref<HTMLDialogElement>();
onMounted(() => element.value?.showModal());
</script>

<template>
  <dialog ref="element" class="um-admin-dialog" :aria-label="title" @cancel.prevent="!busy && emit('close')">
    <header><h2>{{ title }}</h2><button type="button" class="icon" title="关闭" :disabled="busy" @click="emit('close')"><X :size="18" /></button></header>
    <slot />
  </dialog>
</template>
