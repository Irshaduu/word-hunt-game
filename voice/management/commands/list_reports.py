from django.core.management.base import BaseCommand

from voice.models import Report


class Command(BaseCommand):
    help = 'The latest reports from voice rooms, newest first.'

    def add_arguments(self, parser):
        parser.add_argument('--last', type=int, default=50, help='how many (default 50)')

    def handle(self, *args, **options):
        reports = Report.objects.select_related('reporter', 'reported')[:options['last']]
        if not reports:
            self.stdout.write('No reports.')
        for report in reports:
            by = report.reporter.username if report.reporter else '(deleted account)'
            self.stdout.write(f'{report.created_at:%Y-%m-%d %H:%M}  {report.reported.username} '
                              f'in "{report.room_name}", reported by {by}: {report.reason or "(no reason given)"}')
