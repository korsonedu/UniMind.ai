import assert from 'node:assert/strict';
import test from 'node:test';
import { HOME_PATH, getReturnTo, getLoginPath } from '../src/lib/routing.ts';

test('默认进入小宇，回跳保留页面参数和锚点', () => {
  assert.equal(HOME_PATH, '/xiaoyu');
  assert.equal(getReturnTo(null), '/xiaoyu');
  assert.equal(getReturnTo('/qa/42?filter=followed#answer'), '/qa/42?filter=followed#answer');
  assert.equal(getLoginPath('/course/12?lesson=3#video'), '/login?next=%2Fcourse%2F12%3Flesson%3D3%23video');
});

test('拒绝站外回跳和认证页面循环', () => {
  for (const path of [
    'https://example.com', '//example.com', '/\\example.com',
    '/\n/example.com', '/login?next=/qa', '/register/',
    '/verify-code?email=test', '/account-callback', '/qa/../login', '/LOGIN', '/%6cogin',
    '/api/users/me/', '/admin/', '/accounts/login/',
  ]) assert.equal(getReturnTo(path), HOME_PATH, path);
});
