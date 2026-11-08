"""Local prototype state bridge; no generated code receives site credentials."""
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsMember
from .services.learning_experiments import (
    anchor_for, load_experiment, save_experiment, validate_state,
    experiment_document, ExperimentConflict,
)


class ExperimentState(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)
    state_version = serializers.IntegerField(min_value=0)
    state = serializers.JSONField()


class LearningExperimentView(APIView):
    permission_classes = [IsMember]

    def get(self, request, conversation_id, experiment_id):
        anchor = anchor_for(request.user, conversation_id)
        item = load_experiment(anchor, str(experiment_id))
        return Response({key: item[key] for key in ('title', 'revision', 'state', 'state_version')} | {
            'document': experiment_document(item['html'], item['state'])}, headers={'Cache-Control': 'no-store'})

    def patch(self, request, conversation_id, experiment_id):
        data = ExperimentState(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        state = validate_state(values['state'])
        anchor = anchor_for(request.user, conversation_id)
        item = load_experiment(anchor, str(experiment_id))
        if values['revision'] != item['revision'] or values['state_version'] != item['state_version']:
            raise ExperimentConflict()
        updated = {**item, 'state': state, 'state_version': item['state_version'] + 1}
        save_experiment(anchor, str(experiment_id), updated)
        return Response({'state_version': updated['state_version']})
