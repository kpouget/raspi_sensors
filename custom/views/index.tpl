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

  % for metric_id, (metric, entry) in published_metrics:
    
  <form class="form-inline" action="/" method="POST">
    % import json
    % label_dict = dict(zip(metric._labelnames, metric._labelvalues))
    % label_text = ", ".join(f"{k}: {v}" for k, v in label_dict.items())
    % label_text = "{"+label_text+"}" if label_text else ""
    % if entry.get("hidden"):
    % continue
    % end

    <p>
      <input type="hidden" name="what" value="{{ metric_id }}">
      <input type="float" id="{{ metric_id }}" placeholder="{{ metric._documentation}} {{ metric._samples()[0].value }} {{ entry["units"] }}" name="{{ metric_id }}" required>
      <button type="submit">Ajouter</button>
      <br/>
      <label for="{{ metric_id }}">
        {{ metric._documentation}} | <code>{{ metric._name }} {{ label_text }} {{ entry["value"] or 0 }}</code></label>
      <br/>
      % metric_last_update_date = entry["last_update"].get("date") or "(jamais)"
      % metric_last_update_value = entry["last_update"].get("value") or 0
      % metric_last_update_units = entry["units"]
      <b>Dernière mise à jour:</b> +{{metric_last_update_value}} {{ metric_last_update_units}} le {{ metric_last_update_date }}
      </br>
      </p>
  </form>
  <hr/>
  % end
  <form class="form-inline" action="/" method="POST">
    <p>
      Nouvelle métrique:<br/>
      <input type="hidden" name="what" value="__new__">
      <input id="__new__.name" placeholder="Nom de la métrique" name="__new__.name" required>
      <input id="__new__.documentation" placeholder="Description ou 'exit' ou 'delete'" name="__new__.documentation"> 
      <input id="__new__.units" placeholder="Unités" name="__new__.units">
      <button type="submit">Créer</button>
      % for label_id in range(CREATE_LABELS_COUNT):
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
