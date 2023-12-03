<!DOCTYPE html>
<html lang="en-US">
<head>
  <title>Métriques</title>
  <meta name="viewport" content="width=device-width">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel='stylesheet' href='/static/style.css'>
</head>
<body>
  % if msg is not None:
  <p>{{ msg }}</p>
  <hr/>
  % end

  % for metric_id, metric in metrics:
  <form class="form-inline" action="/" method="POST">
    % import json
    % label_dict = dict(zip(metric._labelnames, metric._labelvalues))
    % label_text = ", ".join(f"{k}: {v}" for k, v in label_dict.items())

    <p>
      <input type="hidden" name="what" value="{{ metric_id }}">
      <input type="number" id="{{ metric_id }}" placeholder="{{ metric_id}} ({{ metric._samples()[0].value }})" name="{{ metric_id }}" required>
      <button type="submit">Ajouter</button>
      <br/>
      <label for="{{ metric_id }}"><i>{{ label_text }}</i><br/><b>{{ metric._name }}</b>: {{ metric._documentation}}</label>
      </p>
  </form>
  <hr/>
  % end
  <form class="form-inline" action="/" method="POST">
    <p>
      Nouvelle métrique:<br/>
      <input type="hidden" name="what" value="__new__">
      <input id="__new__.name" placeholder="Nom de la métrique" name="__new__.name" required>
      <input id="__new__.description" placeholder="Description de la métrique" name="__new__.description" required> <button type="submit">Créer</button>
      % for label_id in range(LABELS_COUNT):
        <br/> Label {{ label_id }}:
        <input id="__new__.labelname{{ label_id }}" placeholder="Label #{{ label_id }}" name="__new__.label{{ label_id }}">
        <input id="__new__.labelvalue{{ label_id }}" placeholder="Valeur du label #{{ label_id }}" name="__new__.labelvalue{{ label_id }}">
      % end

      <br/>
      </p>
  </form>
  <hr/>
</body>
</html>
