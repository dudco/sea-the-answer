const messages={
  MODEL_TIMEOUT:['모델 응답 대기 시간이 초과됐습니다. 서버의 모델 적재 상태와 생성 시간 설정을 확인해 주세요.','The model response timed out. Check model loading and the generation time budget.'],
  MODEL_AUTH_FAILED:['모델 서버 인증에 실패했습니다. 관리자가 연결 자격 정보를 확인해야 합니다.','Model authentication failed. Ask an administrator to check its credentials.'],
  MODEL_ENDPOINT_OR_NAME:['모델 주소 또는 모델 이름을 찾지 못했습니다. 서버 연결 설정을 확인해 주세요.','The model endpoint or model name was not found. Check the server configuration.'],
  MODEL_CONNECTION_FAILED:['모델 서버에 연결하지 못했습니다. 모델 서비스와 네트워크 상태를 확인해 주세요.','The model server could not be reached. Check its service and network.'],
  MODEL_REQUEST_REJECTED:['모델 서버가 요청 형식을 거부했습니다. 구조화 출력·토큰·추론 옵션의 호환성을 확인해 주세요.','The model server rejected the request. Check structured-output, token and reasoning options.'],
  MODEL_RATE_LIMITED:['모델 서버의 호출 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.','The model rate limit was reached. Try again later.'],
  MODEL_OUTPUT_TRUNCATED:['모델의 출력이 완성되기 전에 잘렸습니다. 질문 범위나 서버의 출력·추론 설정을 확인해 주세요.','The model output was truncated. Check the question scope and output/reasoning limits.'],
  MODEL_EMPTY_CONTENT:['모델이 최종 답변 내용을 반환하지 않았습니다. 추론 모드와 출력 제한을 확인해 주세요.','The model returned no final answer. Check reasoning mode and output limits.'],
  MODEL_INVALID_JSON:['모델이 요청한 답변 형식을 지키지 못했습니다. 원문 발췌를 확인해 주세요.','The model did not return the required answer format. Review the source excerpts.'],
  MODEL_CITATION_MISMATCH:['모델이 제시한 인용을 원문에서 확인하지 못해 답변을 채택하지 않았습니다.','The generated citation could not be verified in the source, so the answer was not accepted.'],
  MODEL_SERVER_ERROR:['모델 서버에서 오류가 발생했습니다. 관리자 오류 기록을 확인해 주세요.','The model server returned an error. Check the administrator error log.'],
};
export function generationFailureMessage(code,en=false) {
  const value=messages[code];
  return value ? value[en?1:0] : '';
}
