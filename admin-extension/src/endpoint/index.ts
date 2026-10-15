import { defineEndpoint } from '@directus/extensions-sdk';
import { callDjango, configuration } from '../bridge';

export default defineEndpoint((router, { env, logger }) => {
  router.post('/operations/:operation', async (req, res) => {
    try {
      const config = configuration(env);
      const actor = req.accountability?.user;
      if (!req.accountability?.admin || !actor || !config.operators.includes(actor)) {
        res.status(403).json({ error: '当前账号未获授权管理 UniMind。' });
        return;
      }
      const result = await callDjango(config, actor, req.params.operation!, req.body);
      res.status(result.status).json(result.body);
    } catch (error) {
      logger.warn({ message: error instanceof Error ? error.message : 'Management bridge failure' }, 'UniMind bridge unavailable');
      res.status(503).json({ error: 'UniMind 管理连接暂不可用，请检查后台配置。' });
    }
  });
});
