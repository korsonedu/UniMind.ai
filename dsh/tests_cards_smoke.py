"""Only real, permitted tool results may become read-only UI cards."""
import json
import unittest

from cards import tool_cards


class CardsSmoke(unittest.TestCase):
    def test_card_provenance_and_links(self):
        visual = {'type': 'data_card', 'payload': {'title': '课程', 'items': [
            {'label': '久期', 'value': '打开', 'action_link': '/course/1'}]}}

        def events(name='search_courses', value=None, error=False):
            return [{'type': 'tool/call', 'data': {'callId': 'call', 'name': name}},
                    {'type': 'tool/result', 'data': {'meta': {'unimindCard': visual}, 'message': {'role': 'tool',
                        'toolCallId': 'call', 'isError': error, 'content': [
                            {'type': 'text', 'text': json.dumps({'courses': []} if value is None else value)}]}}}]

        context = {'tools': [{'function': {'name': 'search_courses'}}]}
        self.assertEqual(tool_cards(events(), context), [{'tool': 'search_courses', **visual}])
        self.assertEqual(tool_cards(events(name='render_visual'), context), [])
        self.assertEqual(tool_cards(events(error=True), context), [])
        self.assertEqual(tool_cards(events(value={'error': 'denied', 'visual': visual}), context), [])
        self.assertEqual(tool_cards([{'type': 'assistant/message', 'data': {'visual': visual}}], context), [])
        content_only = events()
        content_only[1]['data'].pop('meta')
        content_only[1]['data']['message']['content'][0]['text'] = json.dumps({'visual': visual})
        self.assertEqual(tool_cards(content_only, context), [])
        for link in ('https://example.com', '//example.com', '/course/1?redirect=https://example.com', '/admin'):
            visual['payload']['items'][0]['action_link'] = link
            self.assertEqual(tool_cards(events(), context), [])
        visual['type'] = 'practice_quiz'
        self.assertEqual(tool_cards(events(), context), [])


if __name__ == '__main__':
    unittest.main()
