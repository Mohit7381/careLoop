import { Component, input } from '@angular/core';

import { StageView } from '../../../../core/services/run.service';

@Component({
  selector: 'app-pipeline-tracker',
  templateUrl: './pipeline-tracker.component.html',
  styleUrl: './pipeline-tracker.component.scss',
})
export class PipelineTrackerComponent {
  readonly stages = input.required<StageView[]>();
}
