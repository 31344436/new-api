import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { API, showError } from '../../../../helpers';

export function useEnabledModels() {
  const { t } = useTranslation();
  const [enabledModels, setEnabledModels] = useState([]);

  useEffect(() => {
    let mounted = true;

    const fetchEnabledModels = async () => {
      try {
        const res = await API.get('/api/channel/models_enabled');
        const { success, message, data } = res.data;
        if (!mounted) {
          return;
        }
        if (success) {
          setEnabledModels(Array.isArray(data) ? data : []);
        } else {
          showError(message);
        }
      } catch (error) {
        console.error(t('获取启用模型失败:'), error);
        showError(t('获取启用模型失败'));
      }
    };

    fetchEnabledModels();
    return () => {
      mounted = false;
    };
  }, [t]);

  return enabledModels;
}
